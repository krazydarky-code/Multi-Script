# SPDX-License-Identifier: GPL-3.0-or-later
"""Godot 4 shader library for ms_godot_shader_create (each one is parsed by a real headless Godot in the test-suite)."""

_NOISE2 = '''float hash21(vec2 p) {
	p = fract(p * vec2(123.34, 456.21));
	p += dot(p, p + 45.32);
	return fract(p.x * p.y);
}
float vnoise2(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash21(i), hash21(i + vec2(1.0, 0.0)), f.x), mix(hash21(i + vec2(0.0, 1.0)), hash21(i + vec2(1.0, 1.0)), f.x), f.y);
}
'''
_NOISE3 = '''float hash31(vec3 p) {
	p = fract(p * 0.3183099 + vec3(0.1));
	p *= 17.0;
	return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}
float vnoise3(vec3 x) {
	vec3 i = floor(x);
	vec3 f = fract(x);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(mix(hash31(i), hash31(i + vec3(1.0, 0.0, 0.0)), f.x), mix(hash31(i + vec3(0.0, 1.0, 0.0)), hash31(i + vec3(1.0, 1.0, 0.0)), f.x), f.y),
			   mix(mix(hash31(i + vec3(0.0, 0.0, 1.0)), hash31(i + vec3(1.0, 0.0, 1.0)), f.x), mix(hash31(i + vec3(0.0, 1.0, 1.0)), hash31(i + vec3(1.0, 1.0, 1.0)), f.x), f.y), f.z);
}
'''

SHADERS = {}


def add(name, kind, summary, code):
    SHADERS[name] = {"type": kind, "summary": summary, "code": code.replace("@@NOISE2@@", _NOISE2).replace("@@NOISE3@@", _NOISE3)}


add("toon", "spatial", "Cel shading with toon diffuse/specular and a rim light", '''shader_type spatial;
render_mode diffuse_toon, specular_toon;

uniform vec4 albedo : source_color = vec4(0.9, 0.5, 0.3, 1.0);
uniform sampler2D albedo_tex : source_color, filter_linear_mipmap, repeat_enable;
uniform float roughness : hint_range(0.0, 1.0) = 0.6;
uniform vec4 rim_color : source_color = vec4(1.0, 1.0, 1.0, 1.0);
uniform float rim_power : hint_range(0.5, 8.0) = 3.0;
uniform float rim_strength : hint_range(0.0, 2.0) = 0.6;

void fragment() {
	vec3 tex = texture(albedo_tex, UV).rgb;
	ALBEDO = albedo.rgb * tex;
	ROUGHNESS = roughness;
	float fres = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), rim_power);
	EMISSION = rim_color.rgb * fres * rim_strength;
}
''')

add("outline", "spatial", "Inverted-hull outline (use as next_pass of another material)", '''shader_type spatial;
render_mode unshaded, cull_front;

uniform vec4 outline_color : source_color = vec4(0.0, 0.0, 0.0, 1.0);
uniform float outline_width : hint_range(0.0, 0.2) = 0.03;

void vertex() {
	VERTEX += NORMAL * outline_width;
}

void fragment() {
	ALBEDO = outline_color.rgb;
}
''')

add("dissolve", "spatial", "Noise dissolve with a glowing burn edge", '''shader_type spatial;
render_mode cull_disabled;

uniform vec4 albedo : source_color = vec4(1.0, 1.0, 1.0, 1.0);
uniform float dissolve : hint_range(0.0, 1.0) = 0.3;
uniform float noise_scale = 6.0;
uniform float edge_width : hint_range(0.0, 0.3) = 0.06;
uniform vec4 edge_color : source_color = vec4(1.0, 0.45, 0.1, 1.0);
uniform float edge_energy = 4.0;
varying vec3 local_pos;

@@NOISE3@@
void vertex() {
	local_pos = VERTEX;
}

void fragment() {
	float n = vnoise3(local_pos * noise_scale);
	if (n < dissolve) {
		discard;
	}
	float edge = 1.0 - smoothstep(0.0, edge_width, n - dissolve);
	ALBEDO = albedo.rgb;
	EMISSION = edge_color.rgb * edge * edge_energy;
}
''')

add("hologram", "spatial", "Additive scanline hologram with fresnel and flicker", '''shader_type spatial;
render_mode blend_add, unshaded, cull_disabled, depth_draw_never;

uniform vec4 color : source_color = vec4(0.2, 0.8, 1.0, 1.0);
uniform float fresnel_power = 2.5;
uniform float scan_speed = 0.6;
uniform float scan_density = 40.0;
uniform float flicker_speed = 12.0;
varying vec3 world_pos;

void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	float fres = pow(1.0 - clamp(dot(normalize(NORMAL), normalize(VIEW)), 0.0, 1.0), fresnel_power);
	float scan = 0.5 + 0.5 * sin(world_pos.y * scan_density - TIME * scan_speed * 10.0);
	float flick = 0.85 + 0.15 * sin(TIME * flicker_speed);
	ALBEDO = color.rgb;
	ALPHA = clamp((fres + scan * 0.35) * flick, 0.0, 1.0);
}
''')

add("water", "spatial", "Animated waves with fresnel colour and foam crests", '''shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back;

uniform vec4 shallow_color : source_color = vec4(0.1, 0.55, 0.65, 0.75);
uniform vec4 deep_color : source_color = vec4(0.02, 0.15, 0.3, 0.95);
uniform float wave_height = 0.25;
uniform float wave_speed = 0.8;
uniform float wave_freq = 0.6;
uniform float foam_amount : hint_range(0.0, 1.0) = 0.25;
varying float h;

float wave(vec2 p) {
	return sin(p.x * wave_freq + TIME * wave_speed) * 0.5 + sin(p.y * wave_freq * 1.3 - TIME * wave_speed * 0.8) * 0.5 + sin((p.x + p.y) * wave_freq * 0.7 + TIME * wave_speed * 1.4) * 0.3;
}

void vertex() {
	vec3 wp = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	float e = 0.1;
	h = wave(wp.xz);
	VERTEX.y += h * wave_height;
	float hx = wave(wp.xz + vec2(e, 0.0));
	float hz = wave(wp.xz + vec2(0.0, e));
	NORMAL = normalize(vec3(-(hx - h) * wave_height / e, 1.0, -(hz - h) * wave_height / e));
}

void fragment() {
	float fres = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), 3.0);
	vec4 c = mix(deep_color, shallow_color, fres);
	float foam = smoothstep(1.0 - foam_amount, 1.0, h * 0.5 + 0.5);
	ALBEDO = mix(c.rgb, vec3(1.0), foam * 0.6);
	ALPHA = mix(c.a, 1.0, foam);
	ROUGHNESS = mix(0.05, 0.5, foam);
	METALLIC = 0.0;
	SPECULAR = 0.6;
}
''')

add("rim_glow", "spatial", "Fresnel rim emission for selection / power-up highlights", '''shader_type spatial;

uniform vec4 albedo : source_color = vec4(0.2, 0.2, 0.25, 1.0);
uniform vec4 glow_color : source_color = vec4(0.3, 0.8, 1.0, 1.0);
uniform float glow_power : hint_range(0.5, 8.0) = 2.5;
uniform float glow_energy : hint_range(0.0, 8.0) = 2.0;
uniform float pulse_speed = 2.0;

void fragment() {
	float fres = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), glow_power);
	float pulse = 0.75 + 0.25 * sin(TIME * pulse_speed);
	ALBEDO = albedo.rgb;
	EMISSION = glow_color.rgb * fres * glow_energy * pulse;
}
''')

add("wind_sway", "spatial", "Foliage vertex sway (grass, leaves, flags) with alpha cut-out", '''shader_type spatial;
render_mode cull_disabled;

uniform vec4 albedo : source_color = vec4(0.3, 0.6, 0.2, 1.0);
uniform sampler2D albedo_tex : source_color, filter_linear_mipmap, repeat_enable;
uniform float sway_strength = 0.15;
uniform float sway_speed = 1.5;
uniform float height_scale = 2.0;
uniform float alpha_cut : hint_range(0.0, 1.0) = 0.4;

void vertex() {
	float w = clamp(VERTEX.y / height_scale, 0.0, 1.0);
	vec3 wp = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	float t = TIME * sway_speed + wp.x * 0.5 + wp.z * 0.5;
	VERTEX.x += sin(t) * sway_strength * w * w;
	VERTEX.z += cos(t * 0.8) * sway_strength * 0.6 * w * w;
}

void fragment() {
	vec4 tex = texture(albedo_tex, UV);
	ALBEDO = albedo.rgb * tex.rgb;
	ALPHA = tex.a;
	ALPHA_SCISSOR_THRESHOLD = alpha_cut;
}
''')

add("grid", "spatial", "World-space blockout grid (triplanar), great for greyboxing", '''shader_type spatial;

uniform vec4 base_color : source_color = vec4(0.55, 0.57, 0.6, 1.0);
uniform vec4 line_color : source_color = vec4(0.25, 0.27, 0.3, 1.0);
uniform float cell_size = 1.0;
uniform float line_width : hint_range(0.001, 0.2) = 0.03;
varying vec3 wp;
varying vec3 wn;

void vertex() {
	wp = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	wn = abs(normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz));
}

float grid_line(vec2 p) {
	vec2 f = abs(fract(p / cell_size) - 0.5);
	return step(0.5 - line_width, max(f.x, f.y));
}

void fragment() {
	vec2 p = wp.xy;
	if (wn.y >= wn.x && wn.y >= wn.z) {
		p = wp.xz;
	} else if (wn.x >= wn.z) {
		p = wp.zy;
	}
	ALBEDO = mix(base_color.rgb, line_color.rgb, grid_line(p));
	ROUGHNESS = 0.9;
}
''')

add("outline_2d", "canvas_item", "Sprite outline from neighbouring alpha", '''shader_type canvas_item;

uniform vec4 line_color : source_color = vec4(1.0, 1.0, 1.0, 1.0);
uniform float line_width : hint_range(0.0, 8.0) = 1.0;

void fragment() {
	vec2 px = TEXTURE_PIXEL_SIZE * line_width;
	vec4 c = texture(TEXTURE, UV);
	float a = c.a;
	a = max(a, texture(TEXTURE, UV + vec2(px.x, 0.0)).a);
	a = max(a, texture(TEXTURE, UV - vec2(px.x, 0.0)).a);
	a = max(a, texture(TEXTURE, UV + vec2(0.0, px.y)).a);
	a = max(a, texture(TEXTURE, UV - vec2(0.0, px.y)).a);
	a = max(a, texture(TEXTURE, UV + px).a);
	a = max(a, texture(TEXTURE, UV - px).a);
	a = max(a, texture(TEXTURE, UV + vec2(px.x, -px.y)).a);
	a = max(a, texture(TEXTURE, UV + vec2(-px.x, px.y)).a);
	vec4 o = vec4(line_color.rgb, line_color.a * a);
	COLOR = mix(o, c, c.a);
}
''')

add("flash_white", "canvas_item", "Hit flash: set `flash` 0..1 from code (tween it down)", '''shader_type canvas_item;

uniform vec4 flash_color : source_color = vec4(1.0, 1.0, 1.0, 1.0);
uniform float flash : hint_range(0.0, 1.0) = 0.0;

void fragment() {
	vec4 c = texture(TEXTURE, UV);
	COLOR = vec4(mix(c.rgb, flash_color.rgb, flash), c.a) * COLOR.a;
}
''')

add("dissolve_2d", "canvas_item", "Noise dissolve for sprites with a burning edge", '''shader_type canvas_item;

uniform float dissolve : hint_range(0.0, 1.0) = 0.3;
uniform float noise_scale = 8.0;
uniform float edge_width : hint_range(0.0, 0.3) = 0.06;
uniform vec4 edge_color : source_color = vec4(1.0, 0.5, 0.1, 1.0);

@@NOISE2@@
void fragment() {
	vec4 c = texture(TEXTURE, UV);
	float n = vnoise2(UV * noise_scale);
	float keep = step(dissolve, n);
	float edge = (1.0 - smoothstep(0.0, edge_width, n - dissolve)) * keep;
	COLOR = vec4(mix(c.rgb, edge_color.rgb, edge), c.a * keep);
}
''')

add("pixelate", "canvas_item", "Pixelate a sprite or UI element", '''shader_type canvas_item;

uniform float pixels : hint_range(4.0, 512.0) = 64.0;

void fragment() {
	vec2 uv = floor(UV * pixels) / pixels;
	COLOR = texture(TEXTURE, uv);
}
''')

add("wave_2d", "canvas_item", "Wobbling / underwater distortion for sprites", '''shader_type canvas_item;

uniform float amplitude : hint_range(0.0, 0.2) = 0.02;
uniform float frequency = 18.0;
uniform float speed = 3.0;

void fragment() {
	vec2 uv = UV;
	uv.x += sin(uv.y * frequency + TIME * speed) * amplitude;
	uv.y += cos(uv.x * frequency * 0.8 + TIME * speed) * amplitude * 0.5;
	COLOR = texture(TEXTURE, uv);
}
''')

add("scroll_uv", "canvas_item", "Scrolling texture (conveyors, parallax clouds, waterfalls)", '''shader_type canvas_item;

uniform vec2 scroll = vec2(0.1, 0.0);

void fragment() {
	COLOR = texture(TEXTURE, fract(UV + scroll * TIME));
}
''')

add("glow_pulse", "canvas_item", "Pulsing emissive glow on a sprite", '''shader_type canvas_item;

uniform vec4 glow_color : source_color = vec4(1.0, 0.8, 0.3, 1.0);
uniform float strength : hint_range(0.0, 3.0) = 0.8;
uniform float speed = 3.0;

void fragment() {
	vec4 c = texture(TEXTURE, UV);
	float pulse = 0.5 + 0.5 * sin(TIME * speed);
	c.rgb += glow_color.rgb * pulse * strength * c.a;
	COLOR = c;
}
''')

add("vignette", "canvas_item", "Screen-edge darkening (put on a full-rect ColorRect)", '''shader_type canvas_item;

uniform vec4 vignette_color : source_color = vec4(0.0, 0.0, 0.0, 1.0);
uniform float intensity : hint_range(0.0, 2.0) = 0.9;
uniform float softness : hint_range(0.05, 1.0) = 0.5;

void fragment() {
	float d = distance(UV, vec2(0.5, 0.5)) * 1.4142;
	float v = smoothstep(1.0 - softness, 1.0, d * intensity);
	COLOR = vec4(vignette_color.rgb, v * vignette_color.a);
}
''')

add("crt", "canvas_item", "CRT screen: curvature, scanlines, chromatic aberration (full-rect ColorRect on a CanvasLayer)", '''shader_type canvas_item;

uniform sampler2D screen_tex : hint_screen_texture, repeat_disable, filter_linear;
uniform float curvature : hint_range(0.0, 0.5) = 0.12;
uniform float scanline_strength : hint_range(0.0, 1.0) = 0.25;
uniform float scanline_count = 240.0;
uniform float aberration = 0.0015;

vec2 curve(vec2 uv) {
	uv = uv * 2.0 - 1.0;
	vec2 off = abs(uv.yx) * curvature;
	uv += uv * off * off;
	return uv * 0.5 + 0.5;
}

void fragment() {
	vec2 uv = curve(SCREEN_UV);
	if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
		COLOR = vec4(0.0, 0.0, 0.0, 1.0);
	} else {
		float r = texture(screen_tex, uv + vec2(aberration, 0.0)).r;
		float g = texture(screen_tex, uv).g;
		float b = texture(screen_tex, uv - vec2(aberration, 0.0)).b;
		float s = 1.0 - scanline_strength * (0.5 + 0.5 * sin(uv.y * scanline_count * 3.14159));
		COLOR = vec4(vec3(r, g, b) * s, 1.0);
	}
}
''')

add("color_grade", "canvas_item", "Screen colour grading: brightness, contrast, saturation, tint", '''shader_type canvas_item;

uniform sampler2D screen_tex : hint_screen_texture, repeat_disable, filter_linear;
uniform float brightness : hint_range(-1.0, 1.0) = 0.0;
uniform float contrast : hint_range(0.0, 2.0) = 1.1;
uniform float saturation : hint_range(0.0, 2.0) = 1.1;
uniform vec4 tint : source_color = vec4(1.0, 1.0, 1.0, 1.0);

void fragment() {
	vec3 c = texture(screen_tex, SCREEN_UV).rgb;
	c += brightness;
	c = (c - 0.5) * contrast + 0.5;
	float l = dot(c, vec3(0.299, 0.587, 0.114));
	c = mix(vec3(l), c, saturation) * tint.rgb;
	COLOR = vec4(c, 1.0);
}
''')
