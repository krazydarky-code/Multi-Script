--!nonstrict
-- SPDX-License-Identifier: GPL-3.0-or-later
-- OMNI scalar/vector springs with analytic, frame-step-independent integration.
local Spring = {}; Spring.__index = Spring
local function step(position, velocity, target, frequency, damping, dt)
 assert(dt == dt and dt >= 0 and dt < math.huge, "Finite nonnegative dt required")
 if dt == 0 then return position, velocity end
 local w = 2 * math.pi * frequency
 if w == 0 then return position + velocity * dt, velocity end
 local y = position - target
 if math.abs(damping - 1) < 1e-5 then
  local c = velocity + w * y; local decay = math.exp(-w * dt)
  return target + (y + c * dt) * decay, (velocity - w * c * dt) * decay
 elseif damping < 1 then
  local a = damping * w; local b = w * math.sqrt(1 - damping * damping)
  local s, c = math.sin(b * dt), math.cos(b * dt); local decay = math.exp(-a * dt)
  return target + decay * (y * c + (velocity + a * y) / b * s), decay * (velocity * c - (a * velocity + w * w * y) / b * s)
 else
  local root = math.sqrt(damping * damping - 1)
  local r1, r2 = -w / (damping + root), -w * (damping + root)
  local c1 = (velocity - r2 * y) / (r1 - r2); local c2 = y - c1
  local e1, e2 = math.exp(r1 * dt), math.exp(r2 * dt)
  return target + c1 * e1 + c2 * e2, r1 * c1 * e1 + r2 * c2 * e2
 end
end
function Spring.new(frequency, damping, initial)
 frequency = frequency or 10; damping = damping or 1
 assert(frequency >= 0 and frequency < math.huge and damping >= 0 and damping < math.huge, "Finite nonnegative frequency/damping required")
 initial = initial or 0
 return setmetatable({position = initial, velocity = initial * 0, target = initial, frequency = frequency, damping = damping}, Spring)
end
function Spring:Update(dt)
 self.position, self.velocity = step(self.position, self.velocity, self.target, self.frequency, self.damping, dt)
 return self.position
end
function Spring:SetTarget(value) self.target = value end
function Spring:Impulse(value) self.velocity += value end
function Spring:Reset(position, velocity) self.position = position or self.target; self.velocity = velocity or self.position * 0 end
local VectorSpring = {}
function VectorSpring.new(frequency, damping, initial) return Spring.new(frequency, damping, initial or Vector3.zero) end
return {Spring = Spring, Vector3Spring = VectorSpring}
