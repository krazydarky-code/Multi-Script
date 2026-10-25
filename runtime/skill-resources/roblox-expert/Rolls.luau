--!strict
-- Rolls: weighted random results (eggs, crates, spins) decided on the server, with luck and pity.
-- ModuleScript in ServerScriptService. Luck multiplies only the rare tiers, pity guarantees a rare
-- result after N misses, and odds() gives the true percentages to show players (required for paid rolls).
--
--   local Rolls = require(ServerScriptService.Rolls)
--   local egg = Rolls.table({
--       {id = "Dog", weight = 60, rarity = "common"},
--       {id = "Cat", weight = 30, rarity = "uncommon"},
--       {id = "Dragon", weight = 9, rarity = "rare"},
--       {id = "Phoenix", weight = 1, rarity = "legendary"},
--   }, {luckTiers = {rare = true, legendary = true}, pityAfter = 50, pityTier = "legendary"})
--   local result = egg:roll(player, data.Pity, 1.5)   -- luck 1.5; returns the entry and the new pity count
local Rolls = {}
Rolls.__index = Rolls

type Entry = {id: string, weight: number, rarity: string}
type Options = {luckTiers: {[string]: boolean}?, pityAfter: number?, pityTier: string?}

local rng = Random.new()

function Rolls.table(entries: {Entry}, options: Options?)
	assert(#entries > 0, "Rolls.table needs entries")
	for _, e in ipairs(entries) do
		assert(type(e.weight) == "number" and e.weight > 0, "every entry needs a positive weight: " .. tostring(e.id))
	end
	return setmetatable({entries = entries, options = options or {}}, Rolls)
end

local function weightsFor(self: any, luck: number): ({number}, number)
	local weights, total = {}, 0
	local tiers = self.options.luckTiers or {}
	for i, e in ipairs(self.entries) do
		local w = e.weight * (if tiers[e.rarity] then math.max(luck, 1) else 1)
		weights[i] = w
		total += w
	end
	return weights, total
end

-- Returns the entry and the new pity counter (store it in the player's data).
function Rolls.roll(self: any, _player: Player?, pity: number?, luck: number?): (Entry, number)
	local opts = self.options
	local count = (pity or 0) + 1
	if opts.pityAfter and opts.pityTier and count >= opts.pityAfter then
		local pool = {}
		for _, e in ipairs(self.entries) do
			if e.rarity == opts.pityTier then
				table.insert(pool, e)
			end
		end
		if #pool > 0 then
			return pool[rng:NextInteger(1, #pool)], 0
		end
	end
	local weights, total = weightsFor(self, luck or 1)
	local pick = rng:NextNumber() * total
	for i, w in ipairs(weights) do
		pick -= w
		if pick <= 0 then
			local e = self.entries[i]
			return e, if opts.pityTier and e.rarity == opts.pityTier then 0 else count
		end
	end
	local last = self.entries[#self.entries]
	return last, count
end

-- True percentages per entry for the given luck, for the odds display.
function Rolls.odds(self: any, luck: number?): {{id: string, rarity: string, percent: number}}
	local weights, total = weightsFor(self, luck or 1)
	local out = {}
	for i, e in ipairs(self.entries) do
		table.insert(out, {id = e.id, rarity = e.rarity, percent = math.floor(weights[i] / total * 10000 + 0.5) / 100})
	end
	return out
end

-- Rolls many times and returns the counts; use it to check that the odds match the table.
function Rolls.simulate(self: any, times: number, luck: number?): {[string]: number}
	local counts = {}
	local pity = 0
	for _ = 1, times do
		local e
		e, pity = self:roll(nil, pity, luck)
		counts[e.id] = (counts[e.id] or 0) + 1
	end
	return counts
end

return Rolls
