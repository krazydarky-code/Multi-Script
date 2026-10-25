--!nonstrict
-- SPDX-License-Identifier: GPL-3.0-or-later
-- Adapted from supplied OMNI-GUI: lifecycle ownership, no idle polling.
local Maid = {}
Maid.__index = Maid
local function cleanup(item)
 local kind = typeof(item)
 if kind == "RBXScriptConnection" then item:Disconnect()
 elseif kind == "Instance" then item:Destroy()
 elseif type(item) == "thread" then
  if coroutine.status(item) ~= "dead" and item ~= coroutine.running() then task.cancel(item) end
 elseif type(item) == "function" then item()
 elseif type(item) == "table" then
  if type(item.Destroy) == "function" then item:Destroy()
  elseif type(item.Cancel) == "function" then item:Cancel()
  elseif type(item.Disconnect) == "function" then item:Disconnect()
  else error("Unsupported cleanup task") end
 else error("Unsupported cleanup task") end
end
function Maid.new() return setmetatable({_tasks = {}, _destroyed = false}, Maid) end
function Maid:GiveTask(item)
 assert(item ~= nil, "Task cannot be nil")
 if self._destroyed then cleanup(item) else self._tasks[item] = true end
 return item
end
function Maid:GivePromise(promise)
 assert(type(promise.Cancel) == "function" and type(promise.Finally) == "function", "Promise requires Cancel/Finally")
 self:GiveTask(promise)
 promise:Finally(function() self._tasks[promise] = nil end)
 return promise
end
function Maid:RemoveTask(item)
 if self._tasks[item] then self._tasks[item] = nil; cleanup(item) end
end
function Maid:Destroy()
 if self._destroyed then return end
 self._destroyed = true
 local owned = self._tasks; self._tasks = {}
 for item in pairs(owned) do
  local ok, message = pcall(cleanup, item)
  if not ok then warn("OMNI cleanup: " .. tostring(message)) end
 end
end
function Maid.LinkToInstance(instance)
 local maid = Maid.new()
 maid:GiveTask(instance.Destroying:Connect(function() maid:Destroy() end))
 return maid
end
return Maid
