--!strict
-- HitValidation: the server decides whether a client's "I hit them" is believable.
-- ModuleScript in ServerScriptService. The client only reports the target; the server checks the
-- cooldown, range (with a ping allowance), line of sight, that both are alive, and a per-player rate.
--
--   local Hit = require(ServerScriptService.HitValidation)
--   Remotes.onServer("Swing", {Remotes.Check.instance("Model", workspace)}, function(player, targetModel)
--       local ok, why = Hit.validate(player, targetModel, {range = 8, cooldown = 0.45, damage = 20})
--       if ok then Hit.applyDamage(targetModel, 20, player) end
--   end)
local Players = game:GetService("Players")

type Weapon = {range: number, cooldown: number, damage: number?, needsSight: boolean?}

local Hit = {}
local lastHit: {[Player]: number} = {}
local recent: {[Player]: {number}} = {}
local MAX_HITS_PER_SECOND = 8

local sightParams = RaycastParams.new()
sightParams.FilterType = Enum.RaycastFilterType.Exclude

local function rootOf(model: Instance?): BasePart?
	if model == nil then
		return nil
	end
	local root = model:FindFirstChild("HumanoidRootPart")
	return if root and root:IsA("BasePart") then root else nil
end

local function aliveHumanoid(model: Instance?): Humanoid?
	local hum = model and model:FindFirstChildOfClass("Humanoid")
	return if hum and hum.Health > 0 then hum else nil
end

-- Returns ok, reason.
function Hit.validate(player: Player, target: Instance, weapon: Weapon): (boolean, string)
	local character = player.Character
	if not aliveHumanoid(character) then
		return false, "attacker dead"
	end
	if target == character or not aliveHumanoid(target) then
		return false, "bad target"
	end
	local now = os.clock()
	if now - (lastHit[player] or 0) < weapon.cooldown * 0.9 then
		return false, "cooldown"
	end
	local list = recent[player]
	if list == nil then
		list = {}
		recent[player] = list
	end
	while #list > 0 and now - list[1] > 1 do
		table.remove(list, 1)
	end
	if #list >= MAX_HITS_PER_SECOND then
		return false, "rate"
	end
	local myRoot, theirRoot = rootOf(character), rootOf(target)
	if not (myRoot and theirRoot) then
		return false, "no root"
	end
	-- allow for movement during the client's round trip: speed x ping, capped
	local ping = math.clamp(player:GetNetworkPing(), 0, 0.5)
	local allowance = 4 + math.min(theirRoot.AssemblyLinearVelocity.Magnitude * ping * 2, 12)
	local offset = theirRoot.Position - myRoot.Position
	if offset.Magnitude > weapon.range + allowance then
		return false, "out of range"
	end
	if weapon.needsSight ~= false then
		sightParams.FilterDescendantsInstances = {character :: Instance, target}
		if workspace:Raycast(myRoot.Position, offset, sightParams) then
			return false, "blocked"
		end
	end
	lastHit[player] = now
	table.insert(list, now)
	return true, "ok"
end

-- Damage with a creator tag so kill credit works.
function Hit.applyDamage(target: Instance, amount: number, attacker: Player?)
	local hum = aliveHumanoid(target)
	if hum == nil then
		return
	end
	if attacker then
		hum:SetAttribute("LastAttacker", attacker.UserId)
	end
	hum:TakeDamage(amount)
end

Players.PlayerRemoving:Connect(function(player)
	lastHit[player] = nil
	recent[player] = nil
end)

return Hit
