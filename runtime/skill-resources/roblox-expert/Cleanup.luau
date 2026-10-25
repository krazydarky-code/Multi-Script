--!strict
-- Cleanup: collects connections, instances, threads and functions and removes them all at once.
-- ModuleScript in ReplicatedStorage. Use one per player, per round, per NPC or per open screen so
-- nothing leaks when that thing goes away.
--
--   local Cleanup = require(ReplicatedStorage.Cleanup)
--   local bin = Cleanup.new()
--   bin:add(part.Touched:Connect(onTouched))
--   bin:add(effect)                         -- an Instance: destroyed
--   bin:add(task.delay(5, explode))         -- a thread: cancelled
--   bin:add(function() print("bye") end)    -- a function: called
--   bin:bindTo(character)                   -- clean when the character is destroyed
--   bin:clean()
local Cleanup = {}
Cleanup.__index = Cleanup

export type Cleanup = typeof(setmetatable({} :: {items: {any}, cleaning: boolean}, Cleanup))

function Cleanup.new(): Cleanup
	return setmetatable({items = {}, cleaning = false}, Cleanup)
end

function Cleanup.add<T>(self: Cleanup, item: T): T
	if self.cleaning then
		warn("Cleanup: add() while cleaning; the item is removed immediately")
		Cleanup.removeItem(item)
		return item
	end
	table.insert(self.items, item)
	return item
end

function Cleanup.removeItem(item: any)
	local kind = typeof(item)
	if kind == "RBXScriptConnection" then
		item:Disconnect()
	elseif kind == "Instance" then
		item:Destroy()
	elseif kind == "thread" then
		if coroutine.status(item) ~= "dead" then
			pcall(task.cancel, item)
		end
	elseif kind == "function" then
		item()
	elseif kind == "table" then
		if type(item.Destroy) == "function" then
			item:Destroy()
		elseif type(item.clean) == "function" then
			item:clean()
		end
	end
end

function Cleanup.clean(self: Cleanup)
	if self.cleaning then
		return
	end
	self.cleaning = true
	local items = self.items
	self.items = {}
	for i = #items, 1, -1 do
		local ok, err = pcall(Cleanup.removeItem, items[i])
		if not ok then
			warn("Cleanup: an item failed to clean up:", err)
		end
	end
	self.cleaning = false
end

-- Cleans automatically when the instance is destroyed.
function Cleanup.bindTo(self: Cleanup, instance: Instance)
	self:add(instance.Destroying:Connect(function()
		self:clean()
	end))
end

Cleanup.Destroy = Cleanup.clean

return Cleanup
