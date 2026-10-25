import {build} from 'esbuild';
import {readFile,writeFile} from 'node:fs/promises';
await build({entryPoints:['studio.js'],outfile:'studio.bundle.js',bundle:true,minify:true,format:'esm',target:['chrome110','firefox115','safari16'],legalComments:'eof'});
const three=await readFile('node_modules/three/LICENSE','utf8'),gui=await readFile('node_modules/lil-gui/LICENSE.md','utf8');
await writeFile('THIRD_PARTY_LICENSES.txt','Three.js 0.180.0\n'+three+'\n\nlil-gui 0.21.0\n'+gui);
