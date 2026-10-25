const fs=require('fs'),pw=require('./playwright-env');
if(!process.env.MS_NATIVE_EDITOR_BUNDLE||!fs.existsSync(process.env.MS_NATIVE_EDITOR_BUNDLE))pw.skip('ChatGPT native startup/task roundtrip','Set MS_NATIVE_EDITOR_BUNDLE to the bundled native-prosemirror.mjs fixture');
process.env.MS_TEST_PROVIDER='chatgpt';process.env.MS_TEST_LAYOUT='native';require('./test_agentic_runtime_roundtrip');
