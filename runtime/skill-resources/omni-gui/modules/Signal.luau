--!nonstrict
-- SPDX-License-Identifier: GPL-3.0-or-later
-- Adapted from supplied OMNI-GUI. A connection retains its owning signal.
local Signal = {}; Signal.__index = Signal
function Signal.new() return setmetatable({_connections = {}, _waiters = {}, _destroyed = false}, Signal) end
function Signal:Connect(callback)
 assert(not self._destroyed, "Signal destroyed"); assert(type(callback) == "function", "Callback required")
 local owner = self
 local connection = {Connected = true, _callback = callback, _once = false}
 function connection:Disconnect()
  if not self.Connected then return end
  self.Connected = false; owner._connections[self] = nil
 end
 self._connections[connection] = true
 return connection
end
function Signal:Once(callback)
 local connection = self:Connect(callback); connection._once = true; return connection
end
function Signal:Fire(...)
 if self._destroyed then return end
 local pending = {}; for connection in pairs(self._connections) do table.insert(pending, connection) end
 for _, connection in ipairs(pending) do
  if connection.Connected then
   if connection._once then connection:Disconnect() end
   task.spawn(connection._callback, ...)
  end
 end
 local waiters = self._waiters; self._waiters = {}
 for thread in pairs(waiters) do if coroutine.status(thread) == "suspended" then task.spawn(thread, ...) end end
end
function Signal:Wait()
 assert(not self._destroyed, "Signal destroyed")
 local thread = coroutine.running(); self._waiters[thread] = true
 return coroutine.yield()
end
function Signal:Destroy()
 if self._destroyed then return end
 self._destroyed = true
 for connection in pairs(self._connections) do connection.Connected = false end
 self._connections = {}
 for thread in pairs(self._waiters) do
  if coroutine.status(thread) == "suspended" then task.cancel(thread) end
 end
 self._waiters = {}
end
return Signal
