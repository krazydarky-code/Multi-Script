# Multi-Script 6.48.7 verification

Regression repair for 6.48.6: DeepSeek startup can complete multiple valid read-only discovery calls, including the reported list_commands → list_roblox_studios → ready sequence. The synthetic 20-second minimum and six-turn rolling burst cap are removed. Normal saved pacing preferences and the existing shared send coordination apply. Persisted synthetic spacing/history is migrated without discarding real provider cooldowns, account pauses or active leases.

The full content-script chain tests both engine and chat-only discovery with Ultra task methods still applied. The engine fixture measures send gaps with pacing Off and checks that the 20-second floor is absent. Headless adapter tests retain the one-click image send, acknowledgement, no-replay, quiet-thinking, cancellation and native account-notice safeguards. Worker tests cover migration and real cooldown/lease preservation. These are deterministic fixtures, not live DeepSeek account-safety certification.

Archives, verification receipts and signed local upgrade proofs are delivered separately. GitHub publication remains unavailable while the publishing account is suspended.
