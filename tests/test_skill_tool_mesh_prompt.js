const fs=require("fs"),vm=require("vm");const c={console};vm.createContext(c);vm.runInContext(fs.readFileSync("extension/core/config.js","utf8")+";this.__ZS=ZS",c);
for(const level of ["focused","full","maximum"]) { const p=c.__ZS.skillToolCoveragePrompt(level); if(!p.includes("SKILL + TOOL MESH")||!p.includes("specialist")||p.length<650) throw new Error(level); }
if(!c.__ZS.skillToolCoveragePrompt("bad").includes("FULL")) throw new Error("default");console.log("PASS comprehensive skill/tool mesh prompt levels");
