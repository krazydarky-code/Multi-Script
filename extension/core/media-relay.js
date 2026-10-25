// SPDX-License-Identifier: GPL-3.0-or-later
//
// Media relay (browser side): let the user hand a photo or a video to a chat
// surface that has no file-upload control, or that refuses the file type.
//
// ── The problem ──────────────────────────────────────────────────────────
//
// The user has a screenshot of a broken HUD, or a 15-second clip of a physics
// glitch. Several of the surfaces Multi-Script drives expose NO file input at
// all, and others have an upload control that is hidden, disabled, or silently
// refuses video. So the user describes the thing in prose and the model guesses.
//
// ── The approach ─────────────────────────────────────────────────────────
//
// The relay does NOT forge a File into a framework's upload pipeline. It uses
// the one input path every contenteditable already accepts: a real PASTE. The
// providers already implement that per-site (Gemini dispatches a ClipboardEvent;
// Kimi drives the hidden file input the "+" menu mounts), so the relay's job is
// narrower and harder than "upload a file":
//
//   1. Accept the file the user dropped / pasted / picked.
//   2. Ship the bytes to the local bridge, which sniffs the real type, enforces
//      policy and - for a video - extracts a bounded set of frames.
//   3. Hand the resulting IMAGE payloads back to the provider's own
//      attachImages(), which already knows how THIS site accepts an image.
//   4. Append the relay's plain-text manifest to the outgoing message, so even
//      when a video could only be carried as frames (or not at all), the model
//      is told exactly what the user attached and what it is looking at.
//
// Step 3 is the whole trick. The relay never re-implements per-site attachment;
// it converts a hard problem (no upload control) into the already-solved problem
// (an image paste), which is why it works on every provider without a per-site
// branch here.
//
// ── Why the bridge does the conversion, not this file ────────────────────
//
// Frame extraction needs ffmpeg. A content script cannot spawn a process, and
// shipping ffmpeg.wasm into every page would cost megabytes on every site load
// for a feature most sessions never use. The bridge already runs locally and is
// already a trusted part of the user's machine, so the heavy, optional,
// system-dependent work lives there and this side stays a thin client.
const ZSMediaRelay = (() => {
  "use strict";

  // The bridge serves the relay on its plugin port, which is PORT+1. Kept as a
  // constant here because a content script cannot read bridge.py; if a user
  // relocates the bridge with ZS_BRIDGE_PORT the companion port follows the
  // same +1 convention, and MEDIA_PORT_OVERRIDE lets a future settings field
  // win without a code change.
  const DEFAULT_PORT = 17614;
  let MEDIA_PORT_OVERRIDE = null;

  const BASE = () => "http://127.0.0.1:" + (MEDIA_PORT_OVERRIDE || DEFAULT_PORT);

  // A single staging request carries the whole file as base64. Beyond this the
  // request itself becomes the bottleneck (a content script's fetch has no
  // progress events we can use), so the ceiling is deliberately lower than the
  // bridge's own 24 MB and is checked BEFORE a byte is uploaded, with a message
  // the user can act on.
  const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;

  // Accepted by the relay. Kept in sync with runtime/media_relay.py; the bridge
  // is authoritative and will refuse anything else, but telling the user up
  // front beats a round trip that ends in "not supported".
  const IMAGE_MIME = /^image\/(png|jpeg|jpg|gif|webp|bmp)$/i;
  const VIDEO_MIME = /^video\/(mp4|webm|avi|quicktime|x-msvideo)$/i;

  const SETTINGS = {
    enabled: true,
    // Relay the manifest text alongside the pasted media, so the model knows
    // what it is looking at and what was NOT carried.
    sendManifest: true,
    // Auto-clear the bridge spool after a successful attach.
    releaseAfterSend: true,
  };

  function sanitizeSettings(raw) {
    const s = Object.assign({}, SETTINGS, raw && typeof raw === "object" ? raw : {});
    s.enabled = !!s.enabled;
    s.sendManifest = !!s.sendManifest;
    s.releaseAfterSend = !!s.releaseAfterSend;
    return s;
  }

  function setPort(port) {
    const n = parseInt(port, 10);
    MEDIA_PORT_OVERRIDE = Number.isFinite(n) && n > 0 && n < 65536 ? n : null;
  }

  // ── classification ─────────────────────────────────────────────────────
  function classify(file) {
    const type = String((file && file.type) || "");
    const name = String((file && file.name) || "");
    if (IMAGE_MIME.test(type)) return "image";
    if (VIDEO_MIME.test(type)) return "video";
    // Some drops carry an empty MIME; fall back to the extension, but the
    // bridge re-decides from the bytes, so this only shapes the first message.
    if (/\.(png|jpe?g|gif|webp|bmp)$/i.test(name)) return "image";
    if (/\.(mp4|webm|avi|mov)$/i.test(name)) return "video";
    return "unknown";
  }

  function rejectionFor(file) {
    if (!file) return "no file was provided";
    const kind = classify(file);
    if (kind === "unknown") return "That is not a photo or a video. The relay accepts png, jpeg, gif, webp, bmp, mp4, webm, avi and mov.";
    if (file.size > MAX_UPLOAD_BYTES) {
      return "That file is " + formatBytes(file.size) + ". The relay accepts up to " + formatBytes(MAX_UPLOAD_BYTES) + " per file.";
    }
    if (!file.size) return "That file is empty.";
    return null;
  }

  function formatBytes(n) {
    if (!n) return "0 B";
    if (n < 1024) return n + " B";
    if (n < 1048576) return (n / 1024).toFixed(1) + " KB";
    return (n / 1048576).toFixed(1) + " MB";
  }

  // ── transport ──────────────────────────────────────────────────────────
  // Every bridge call is bounded. A dead bridge must surface as a sentence the
  // user can act on ("is the bridge running?"), never as a hang.
  const TIMEOUT_MS = 90000;

  async function bridgeCall(route, payload, timeoutMs) {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), timeoutMs || TIMEOUT_MS);
    try {
      const res = await fetch(BASE() + route, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {}),
        signal: ctl.signal,
      });
      const text = await res.text();
      let data = null;
      try { data = text ? JSON.parse(text) : {}; } catch { data = { raw: text }; }
      if (!res.ok) {
        const msg = (data && data.error) || ("the bridge returned " + res.status);
        const err = new Error(msg);
        err.status = res.status;
        err.data = data;
        throw err;
      }
      return data;
    } catch (e) {
      if (e && e.name === "AbortError") {
        throw new Error("The bridge did not answer in time. Check that the Multi-Script bridge is running, then try again.");
      }
      if (e && e.status) throw e;
      // A thrown fetch here is almost always "nothing is listening on the port".
      throw new Error("Could not reach the local bridge for the media relay. Start the Multi-Script bridge, then try again.");
    } finally {
      clearTimeout(timer);
    }
  }

  function readAsDataUrl(file) {
    return new Promise((resolve, reject) => {
      const fr = new FileReader();
      fr.onload = () => resolve(String(fr.result || ""));
      fr.onerror = () => reject(new Error("the file could not be read"));
      fr.readAsDataURL(file);
    });
  }

  // ── the relay ──────────────────────────────────────────────────────────
  //
  // relayFile(file, {onStage}) -> {
  //   ok, kind, item, payloads: [{mime, dataUrl}], manifest, note, error
  // }
  //
  // The payloads are in the shape providers already consume: `mimeType` +
  // bare base64, so a provider's own fileFromImage() works unchanged.
  async function relayFile(file, opts) {
    const options = opts || {};
    const rejection = rejectionFor(file);
    if (rejection) return { ok: false, kind: "unknown", error: rejection, payloads: [], manifest: "" };

    const kind = classify(file);
    if (typeof options.onStage === "function") {
      try { options.onStage({ phase: "reading", kind, name: file.name, bytes: file.size }); } catch {}
    }

    const dataUrl = await readAsDataUrl(file);
    const comma = dataUrl.indexOf(",");
    const b64 = comma === -1 ? "" : dataUrl.slice(comma + 1);

    if (typeof options.onStage === "function") {
      try { options.onStage({ phase: "uploading", kind, name: file.name, bytes: file.size }); } catch {}
    }

    const staged = await bridgeCall("/media/stage", {
      name: file.name || "",
      mime: file.type || "",
      dataUrl: b64,
    });
    const item = staged && staged.item;
    if (!item || !item.id) return { ok: false, kind, error: "the bridge did not return a staged item", payloads: [], manifest: "" };

    if (typeof options.onStage === "function") {
      try { options.onStage({ phase: "converting", kind, name: item.name, bytes: item.bytes }); } catch {}
    }

    const prepared = (await bridgeCall("/media/prepare", { id: item.id }, 180000)) || {};
    const prep = prepared.prepared || {};

    // Convert the bridge's payloads into the providers' {mimeType, data} shape.
    const payloads = (prep.payloads || []).map((p) => {
      const url = p.dataUrl || "";
      const c = url.indexOf(",");
      return { mimeType: p.mime || "image/jpeg", data: c === -1 ? "" : url.slice(c + 1) };
    }).filter((p) => p.data);

    return {
      ok: payloads.length > 0,
      kind,
      item,
      payloads,
      manifest: prep.manifest || "",
      note: prep.note || "",
      // A staged item with zero payloads is a real, explainable outcome (a
      // video with no ffmpeg). Surface it rather than reporting a bare failure.
      emptyReason: payloads.length ? "" : (prep.note || "no image could be produced from that file"),
      error: payloads.length ? "" : (prep.note || "no image could be produced from that file"),
    };
  }

  async function release(itemId) {
    try {
      await bridgeCall("/media/release", itemId ? { id: itemId } : {});
      return true;
    } catch {
      return false;
    }
  }

  async function stats() {
    try {
      const r = await fetch(BASE() + "/media/stats", { method: "GET" });
      if (!r.ok) return null;
      // Parse the text ourselves rather than r.json(): every bridge response
      // goes through the same decode, and a body that is not JSON (a proxy
      // error page, a half-written response) degrades to null instead of
      // throwing out of a status probe.
      const text = await r.text();
      return text ? JSON.parse(text) : null;
    } catch {
      return null;
    }
  }

  // Compose the text the loop should actually send: the user's own words, then
  // the relay manifest. The manifest is additive and never replaces the request.
  function withManifest(text, relayResult) {
    const base = String(text == null ? "" : text);
    if (!relayResult || !relayResult.manifest) return base;
    return base + "\n\n---\n" + relayResult.manifest;
  }

  // A short, honest line for the panel: what happened, in the user's terms.
  function describeOutcome(result) {
    if (!result) return "Nothing was relayed yet.";
    if (result.ok) {
      if (result.kind === "video") {
        return "Relayed a clip as " + result.payloads.length + " frame" + (result.payloads.length === 1 ? "" : "s") + ", ready to paste.";
      }
      return "Relayed a photo, ready to paste.";
    }
    return result.error || "The file could not be relayed.";
  }

  return {
    DEFAULT_PORT, MAX_UPLOAD_BYTES, SETTINGS,
    sanitizeSettings, setPort, classify, rejectionFor, formatBytes,
    relayFile, release, stats, withManifest, describeOutcome,
    // For tests and the panel.
    IMAGE_MIME, VIDEO_MIME,
  };
})();
