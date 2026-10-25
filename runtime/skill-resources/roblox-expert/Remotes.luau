--!strict
-- Remotes: one place that creates, validates and rate-limits every RemoteEvent / RemoteFunction.
-- ModuleScript in ReplicatedStorage. The server creates the remotes; clients only find them.
--
-- Server:
--   local Remotes = require(ReplicatedStorage.Remotes)
--   local Check = Remotes.Check
--   Remotes.onServer("BuyItem", {Check.string(40)}, function(player, itemId)
--       -- itemId is already a string of at most 40 characters; still check ownership and price here
--   end, {rate = 4, burst = 6})
--   Remotes.fire(player, "Toast", "Bought!")          -- to one player
--   Remotes.fireAll("RoundState", "Playing")           -- to everyone
-- Client:
--   Remotes.send("BuyItem", "sword")
--   Remotes.onClient("Toast", function(text) ... end)
--   local ok, result = Remotes.request("GetProfile")   -- RemoteFunction, server -> client answer
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")

local IS_SERVER = RunService:IsServer()
local FOLDER_NAME = "Remotes"

local Remotes = {}

-- ------------------------------------------------------------------ validators
-- Each validator returns true when the value is acceptable. NaN and infinity are always rejected.
type Validator = (value: any) -> boolean
local Check = {}
Remotes.Check = Check

local function finite(n: number): boolean
	return n == n and n ~= math.huge and n ~= -math.huge
end

function Check.number(min: number?, max: number?): Validator
	return function(v)
		return type(v) == "number" and finite(v) and (min == nil or v >= min) and (max == nil or v <= max)
	end
end

function Check.integer(min: number?, max: number?): Validator
	local isNumber = Check.number(min, max)
	return function(v)
		return isNumber(v) and math.floor(v) == v
	end
end

function Check.string(maxLength: number?): Validator
	return function(v)
		return type(v) == "string" and #v <= (maxLength or 200) and utf8.len(v) ~= nil
	end
end

function Check.boolean(): Validator
	return function(v)
		return type(v) == "boolean"
	end
end

-- One of a fixed list of values, for example Check.oneOf({"sword", "bow"}).
function Check.oneOf(list: {any}): Validator
	local set = {}
	for _, value in ipairs(list) do
		set[value] = true
	end
	return function(v)
		return set[v] == true
	end
end

-- An Instance of a class; with a root, it must also be inside that root (for example workspace.Shops).
function Check.instance(className: string, root: Instance?): Validator
	return function(v)
		return typeof(v) == "Instance" and v:IsA(className) and (root == nil or v:IsDescendantOf(root))
	end
end

function Check.vector3(maxMagnitude: number?): Validator
	return function(v)
		return typeof(v) == "Vector3" and finite(v.X) and finite(v.Y) and finite(v.Z) and (maxMagnitude == nil or v.Magnitude <= maxMagnitude)
	end
end

function Check.optional(inner: Validator): Validator
	return function(v)
		return v == nil or inner(v)
	end
end

-- ------------------------------------------------------------------ folder and remotes
local function folder(): Folder
	local existing = script:FindFirstChild(FOLDER_NAME)
	if existing then
		return existing :: Folder
	end
	if not IS_SERVER then
		return script:WaitForChild(FOLDER_NAME) :: Folder
	end
	local f = Instance.new("Folder")
	f.Name = FOLDER_NAME
	f.Parent = script
	return f
end

local function remote(name: string, className: string): Instance
	local f = folder()
	local found = f:FindFirstChild(name)
	if found then
		return found
	end
	if not IS_SERVER then
		local waited = f:WaitForChild(name, 10)
		assert(waited, "Remotes: the server never created " .. name)
		return waited
	end
	local r = Instance.new(className)
	r.Name = name
	r.Parent = f
	return r
end

-- ------------------------------------------------------------------ rate limiting (token bucket per player per remote)
type Bucket = {tokens: number, last: number}
local buckets: {[Player]: {[string]: Bucket}} = {}

local function allow(player: Player, name: string, rate: number, burst: number): boolean
	local perPlayer = buckets[player]
	if perPlayer == nil then
		perPlayer = {}
		buckets[player] = perPlayer
	end
	local now = os.clock()
	local b = perPlayer[name]
	if b == nil then
		b = {tokens = burst, last = now}
		perPlayer[name] = b
	end
	b.tokens = math.min(burst, b.tokens + (now - b.last) * rate)
	b.last = now
	if b.tokens < 1 then
		return false
	end
	b.tokens -= 1
	return true
end

if IS_SERVER then
	Players.PlayerRemoving:Connect(function(player)
		buckets[player] = nil
	end)
end

local function valid(validators: {Validator}, args: {any}, count: number): boolean
	if count > #validators then
		return false
	end
	for i, check in ipairs(validators) do
		if not check(args[i]) then
			return false
		end
	end
	return true
end

-- ------------------------------------------------------------------ server API
type Options = {rate: number?, burst: number?, unreliable: boolean?}

-- handler(player, ...) runs only when every argument passes its validator and the player is within the rate limit.
function Remotes.onServer(name: string, validators: {Validator}, handler: (Player, ...any) -> (), options: Options?)
	assert(IS_SERVER, "Remotes.onServer runs on the server")
	local opts = options or {}
	local rate, burst = opts.rate or 5, opts.burst or 10
	local r = remote(name, if opts.unreliable then "UnreliableRemoteEvent" else "RemoteEvent") :: RemoteEvent
	r.OnServerEvent:Connect(function(player, ...)
		local args = table.pack(...)
		if not allow(player, name, rate, burst) then
			return
		end
		if not valid(validators, args, args.n) then
			warn(("Remotes: rejected %s from %s (bad arguments)"):format(name, player.Name))
			return
		end
		handler(player, table.unpack(args, 1, args.n))
	end)
end

-- handler(player, ...) returns the answer. Clients wait for it, so keep it quick and never yield for long.
function Remotes.onRequest(name: string, validators: {Validator}, handler: (Player, ...any) -> ...any, options: Options?)
	assert(IS_SERVER, "Remotes.onRequest runs on the server")
	local opts = options or {}
	local rate, burst = opts.rate or 3, opts.burst or 6
	local r = remote(name, "RemoteFunction") :: RemoteFunction
	r.OnServerInvoke = function(player, ...)
		local args = table.pack(...)
		if not allow(player, name, rate, burst) or not valid(validators, args, args.n) then
			return nil
		end
		return handler(player, table.unpack(args, 1, args.n))
	end
end

function Remotes.fire(player: Player, name: string, ...: any)
	(remote(name, "RemoteEvent") :: RemoteEvent):FireClient(player, ...)
end

function Remotes.fireAll(name: string, ...: any)
	(remote(name, "RemoteEvent") :: RemoteEvent):FireAllClients(...)
end

-- Creates the remotes up front so clients never wait for them.
function Remotes.declare(names: {string})
	assert(IS_SERVER, "Remotes.declare runs on the server")
	for _, name in ipairs(names) do
		remote(name, "RemoteEvent")
	end
end

-- ------------------------------------------------------------------ client API
function Remotes.send(name: string, ...: any)
	(remote(name, "RemoteEvent") :: RemoteEvent):FireServer(...)
end

function Remotes.onClient(name: string, handler: (...any) -> ()): RBXScriptConnection
	return (remote(name, "RemoteEvent") :: RemoteEvent).OnClientEvent:Connect(handler)
end

-- Returns ok, ...answer. ok is false when the call errors (for example the server is shutting down).
function Remotes.request(name: string, ...: any): (boolean, ...any)
	local r = remote(name, "RemoteFunction") :: RemoteFunction
	return pcall(r.InvokeServer, r, ...)
end

return Remotes
