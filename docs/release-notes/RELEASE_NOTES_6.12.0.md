# Multi-Script 6.12.0 — Arena Model-Targeted Direct Max Profiles

- Corrected Arena’s starter architecture: **Claude Opus 5.5 is again the default selected target**, not untargeted Direct Max.
- Claude Opus 5.5, Claude Opus 5, GPT-5.6 Sol, Kimi K3 and GPT-6 Luna each retain their own selectable Arena starter profile.
- The selected exact-model request is now re-applied on every turn together with the prompt’s genuine capability mix, giving Arena Direct Max the strongest honest prompt-level signal to route toward that requested model.
- Untargeted Direct Max remains an optional profile rather than replacing model selection.
- Arena still controls the actual backend. Multi-Script does not click the picker, fabricate task requirements, claim an unconfirmed model, or bypass access controls.
- Notion Auto profiles remain completely separate and unchanged.
