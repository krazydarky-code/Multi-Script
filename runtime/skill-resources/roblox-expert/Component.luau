--!strict
-- Component: gives every instance with a CollectionService tag its own object, created when the
-- instance appears (including streamed-in parts) and cleaned up when it leaves. ModuleScript in
-- ReplicatedStorage; works on the server and the client.
--
--   local Component = require(ReplicatedStorage.Component)
--   Component.bind("Lava", function(part, bin)          -- bin is a Cleanup for this instance
--       bin:add(part.Touched:Connect(function(hit)
--           local hum = hit.Parent and hit.Parent:FindFirstChildOfClass("Humanoid")
--           if hum then hum.Health = 0 end
--       end))
--   end)
local CollectionService = game:GetService("CollectionService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Cleanup = require(ReplicatedStorage:WaitForChild("Cleanup"))

local Component = {}
local bound: {[string]: {[Instance]: any}} = {}

-- setup(instance, bin) runs once per tagged instance; anything added to bin is removed with it.
function Component.bind(tag: string, setup: (Instance, any) -> ()): () -> ()
	assert(bound[tag] == nil, "Component: tag already bound: " .. tag)
	local active: {[Instance]: any} = {}
	bound[tag] = active
	local function added(instance: Instance)
		if active[instance] then
			return
		end
		local bin = Cleanup.new()
		active[instance] = bin
		local ok, err = pcall(setup, instance, bin)
		if not ok then
			warn(("Component %s failed on %s: %s"):format(tag, instance:GetFullName(), tostring(err)))
		end
	end
	local function removed(instance: Instance)
		local bin = active[instance]
		if bin then
			active[instance] = nil
			bin:clean()
		end
	end
	local addedConnection = CollectionService:GetInstanceAddedSignal(tag):Connect(added)
	local removedConnection = CollectionService:GetInstanceRemovedSignal(tag):Connect(removed)
	for _, instance in ipairs(CollectionService:GetTagged(tag)) do
		task.spawn(added, instance)
	end
	return function()
		addedConnection:Disconnect()
		removedConnection:Disconnect()
		for instance in pairs(active) do
			removed(instance)
		end
		bound[tag] = nil
	end
end

return Component
