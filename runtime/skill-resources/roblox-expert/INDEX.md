# Expert Roblox modules (Multi-Script)

Production-quality starting points. Read the one you need with ms_skill_reference (skill code-quality or scripting-power, path = file name), then adapt names and config to the project. Every file passes the Multi-Script Luau analyzer and the offline API check; none of them has been run in a live game by Multi-Script, so play-test what you build.

| file | where it goes | what it gives you |
|---|---|---|
| Remotes.luau | ReplicatedStorage (ModuleScript) | creates every remote on the server; argument validators (number, integer, string, boolean, oneOf, instance, vector3, optional) that reject NaN; per-player token-bucket rate limits; RemoteFunction requests with pcall on the client |
| PlayerData.luau | ServerScriptService | session-locked saves with UpdateAsync, retries with backoff, template reconcile, version migration, autosave, BindToClose, kick instead of saving over data that failed to load, Studio fallback |
| Purchases.luau | ServerScriptService | the single ProcessReceipt, idempotent by PurchaseId, granted only after the save succeeds; cached game pass ownership with purchase-finished updates |
| Cleanup.luau | ReplicatedStorage | one bin for connections, instances, threads and functions; bindTo(instance) cleans when it is destroyed |
| RoundSystem.luau | ServerScriptService | Waiting, Intermission, Playing, Ended loop; state on ReplicatedStorage.RoundState attributes for UI; alive tracking, early end, winners callback |
| NpcBrain.luau | ServerScriptService | Patrol, Chase, Attack, Return states; PathfindingService with blocked-path and stuck handling; line-of-sight raycasts; server network ownership |
| HitValidation.luau | ServerScriptService | cooldown, rate, range with ping allowance, line of sight and alive checks for client-reported hits; damage with attacker tag |
| Rolls.luau | ServerScriptService | weighted rolls with luck on rare tiers, pity, true odds for display, and a simulate() check |
| Leaderboard.luau | ServerScriptService | OrderedDataStore top list with throttled writes, cached names, JSON attribute for client UI |
| DailyReward.luau | ServerScriptService | UTC-day claim with streak cycle and a status() for the UI; needs PlayerData |
| UIController.luau | ReplicatedStorage (client use) | one screen open at a time, open and close animation, gamepad focus, B to go back, input-type change event |
| Component.luau | ReplicatedStorage | CollectionService tag binder with a Cleanup per instance (works with streaming) |

Typical server setup: Remotes + PlayerData + Purchases first, then the game systems. Client setup: Remotes + UIController (+ ForgeKit for art).
