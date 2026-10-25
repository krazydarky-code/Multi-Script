--!strict
-- NpcBrain: a server-side NPC with Patrol -> Chase -> Attack -> Return states, real pathfinding,
-- line-of-sight checks and throttled path recomputes. ModuleScript in ServerScriptService.
--
--   local NpcBrain = require(ServerScriptService.NpcBrain)
--   local brain = NpcBrain.new(workspace.Zombie, {
--       patrolPoints = workspace.ZombiePath:GetChildren(),  -- Parts
--       sightRange = 60, attackRange = 5, damage = 15, attackCooldown = 1.2,
--       walkSpeed = 10, chaseSpeed = 16,
--   })
--   brain:start()   -- brain:stop() to end it; it also stops when the NPC dies or is removed
local Players = game:GetService("Players")
local PathfindingService = game:GetService("PathfindingService")

type Options = {
	patrolPoints: {Instance}?, sightRange: number?, loseRange: number?, attackRange: number?, damage: number?,
	attackCooldown: number?, walkSpeed: number?, chaseSpeed: number?, agentRadius: number?, agentHeight: number?,
	canJump: boolean?, onAttack: ((target: Model) -> ())?,
}

local NpcBrain = {}
NpcBrain.__index = NpcBrain

function NpcBrain.new(model: Model, options: Options?)
	local opts = options or {}
	local humanoid = model:FindFirstChildOfClass("Humanoid")
	local root = model:FindFirstChild("HumanoidRootPart")
	assert(humanoid and root and root:IsA("BasePart"), "NpcBrain needs a Humanoid and a HumanoidRootPart")
	local self = setmetatable({}, NpcBrain)
	self.model = model
	self.humanoid = humanoid
	self.root = root
	self.opts = opts
	self.state = "Patrol"
	self.target = nil :: Model?
	self.running = false
	self.lastAttack = 0
	self.patrolIndex = 1
	self.home = root.Position
	self.path = PathfindingService:CreatePath({
		AgentRadius = opts.agentRadius or 2,
		AgentHeight = opts.agentHeight or 5,
		AgentCanJump = if opts.canJump == nil then true else opts.canJump,
		WaypointSpacing = 4,
	})
	self.sightParams = RaycastParams.new()
	self.sightParams.FilterType = Enum.RaycastFilterType.Exclude
	self.sightParams.FilterDescendantsInstances = {model}
	return self
end

-- the closest visible player character in range, or nil
function NpcBrain.findTarget(self: any): Model?
	local best, bestDistance = nil, self.opts.sightRange or 60
	for _, player in ipairs(Players:GetPlayers()) do
		local character = player.Character
		local hum = character and character:FindFirstChildOfClass("Humanoid")
		local hrp = character and character:FindFirstChild("HumanoidRootPart")
		if character and hum and hum.Health > 0 and hrp and hrp:IsA("BasePart") then
			local offset = hrp.Position - self.root.Position
			local distance = offset.Magnitude
			if distance < bestDistance then
				local hit = workspace:Raycast(self.root.Position, offset, self.sightParams)
				if hit == nil or hit.Instance:IsDescendantOf(character) then
					best, bestDistance = character, distance
				end
			end
		end
	end
	return best
end

-- Walks along a computed path; returns early when `keepGoing` says stop. Returns true when it arrived.
function NpcBrain.walkTo(self: any, goal: Vector3, keepGoing: () -> boolean): boolean
	local ok = pcall(function()
		self.path:ComputeAsync(self.root.Position, goal)
	end)
	if not ok or self.path.Status ~= Enum.PathStatus.Success then
		self.humanoid:MoveTo(goal) -- no path: try a straight line once
		self.humanoid.MoveToFinished:Wait()
		return false
	end
	local blocked = false
	local blockedConnection = self.path.Blocked:Connect(function()
		blocked = true
	end)
	for _, waypoint in ipairs(self.path:GetWaypoints()) do
		if blocked or not self.running or not keepGoing() then
			break
		end
		if waypoint.Action == Enum.PathWaypointAction.Jump then
			self.humanoid.Jump = true
		end
		self.humanoid:MoveTo(waypoint.Position)
		local arrived = false
		local finished = self.humanoid.MoveToFinished:Connect(function()
			arrived = true
		end)
		local deadline = os.clock() + 2
		while not arrived and os.clock() < deadline and self.running and keepGoing() do
			task.wait(0.05)
		end
		finished:Disconnect()
		if not arrived then
			break -- stuck: recompute from where we are
		end
	end
	blockedConnection:Disconnect()
	return (self.root.Position - goal).Magnitude < 4
end

function NpcBrain.attack(self: any, target: Model)
	local now = os.clock()
	if now - self.lastAttack < (self.opts.attackCooldown or 1.2) then
		return
	end
	self.lastAttack = now
	local hum = target:FindFirstChildOfClass("Humanoid")
	if hum and hum.Health > 0 then
		hum:TakeDamage(self.opts.damage or 15)
		if self.opts.onAttack then
			task.spawn(self.opts.onAttack, target)
		end
	end
end

function NpcBrain.step(self: any)
	local target = self:findTarget()
	if target then
		self.target = target
		self.state = "Chase"
	elseif self.state == "Chase" then
		self.state = "Return"
	end

	if self.state == "Chase" and self.target then
		local hrp = self.target:FindFirstChild("HumanoidRootPart")
		if not (hrp and hrp:IsA("BasePart")) then
			self.state = "Return"
			return
		end
		local distance = (hrp.Position - self.root.Position).Magnitude
		self.humanoid.WalkSpeed = self.opts.chaseSpeed or 16
		if distance <= (self.opts.attackRange or 5) then
			self.humanoid:MoveTo(self.root.Position) -- stop and swing
			self:attack(self.target)
			task.wait(0.2)
		elseif distance > (self.opts.loseRange or 90) then
			self.state = "Return"
		else
			local startGoal = hrp.Position
			-- recompute when the target moved more than 6 studs from the path goal
			self:walkTo(startGoal, function()
				return (hrp.Position - startGoal).Magnitude < 6 and self:findTarget() ~= nil
			end)
		end
	elseif self.state == "Return" then
		self.humanoid.WalkSpeed = self.opts.walkSpeed or 10
		if self:walkTo(self.home, function() return self:findTarget() == nil end) then
			self.state = "Patrol"
		end
	else
		self.humanoid.WalkSpeed = self.opts.walkSpeed or 10
		local points = self.opts.patrolPoints
		if points and #points > 0 then
			local point = points[self.patrolIndex]
			if point and point:IsA("BasePart") then
				self:walkTo(point.Position, function() return self:findTarget() == nil end)
			end
			self.patrolIndex = self.patrolIndex % #points + 1
			task.wait(1)
		else
			task.wait(0.5)
		end
	end
end

function NpcBrain.start(self: any)
	if self.running then
		return
	end
	self.running = true
	if self.root:CanSetNetworkOwnership() then
		self.root:SetNetworkOwner(nil) -- the server moves NPCs; no client can push them around
	end
	self.diedConnection = self.humanoid.Died:Connect(function()
		self:stop()
	end)
	task.spawn(function()
		while self.running and self.model.Parent and self.humanoid.Health > 0 do
			local ok, err = pcall(self.step, self)
			if not ok then
				warn("NpcBrain:", err)
				task.wait(1)
			end
			task.wait(0.1)
		end
		self.running = false
	end)
end

function NpcBrain.stop(self: any)
	self.running = false
	if self.diedConnection then
		self.diedConnection:Disconnect()
		self.diedConnection = nil
	end
end

return NpcBrain
