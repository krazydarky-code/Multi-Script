import gzip, json, os, pathlib, subprocess, sys, tempfile, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'runtime'))
import omni_gui

class OmniTests(unittest.TestCase):
    def test_reference_index_is_complete_bounded_and_lazy(self):
        self.assertEqual(len(omni_gui.catalog()['references']),522)
        self.assertLess((omni_gui.HERE/'catalog.json.gz').stat().st_size,200000)
        result=json.loads(omni_gui.call({'action':'references','query':'inventory','limit':3})['text'])
        self.assertEqual(len(result['references']),3);self.assertIn('approximate',result['policy'])
        self.assertTrue(all(row.get('sourceUrl') or row.get('source') for row in result['references']))
        with self.assertRaises(ValueError):omni_gui.references({'limit':400})
    def test_no_fake_install_or_user_namespace_overwrite(self):
        result=omni_gui.bundle('UserRequestedKit')
        self.assertIn('assert(not RS:FindFirstChild',result['code'])
        self.assertIn('item.Source == source',result['code']);self.assertFalse(result['verified'])
        self.assertEqual(result['moduleCount'],6)
        self.assertNotIn('_G.OMNI',result['code']);self.assertNotIn('RemoteEvent',result['code'])
        self.assertNotIn('Heartbeat:Connect',result['code'])
        with self.assertRaises(ValueError):omni_gui.bundle('../escape')
        with self.assertRaises(ValueError):omni_gui.call({'action':'install'})
        actual={'text':'{"ok":false,"error":"Studio disconnected"}','images':[]}
        self.assertIs(omni_gui.call({'action':'install'},install=lambda *_:actual),actual)
    def test_source_access_is_bounded(self):
        r=json.loads(omni_gui.call({'action':'modules','module':'Toolkit','max_chars':1000})['text'])
        self.assertEqual(len(r['text']),1000);self.assertEqual(r['next_offset'],1000)
        with self.assertRaises(ValueError):omni_gui.call({'action':'modules','module':'../../config'})
    def test_all_reviewed_luau_compiles_and_lifecycle_executes(self):
        executable=os.environ.get('LUAU_BIN')
        if not executable:self.skipTest('Set LUAU_BIN to official Luau CLI for native module execution.')
        compiler=pathlib.Path(executable).with_name('luau-compile'+('.exe' if os.name=='nt' else ''))
        for module in omni_gui.MODULES:
            r=subprocess.run([str(compiler),str(omni_gui.HERE/'modules'/(module+'.luau')),'--null'],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        code='''local task = {}
function task.spawn(callback, ...) if type(callback) == "thread" then assert(coroutine.resume(callback, ...)) else callback(...) end end
function task.cancel(thread) assert(coroutine.close(thread)) end
local typeof = type
local warnings = 0
local function warn(_) warnings += 1 end
'''
        for name in ('Maid','Signal','Spring'):
            code+='\nlocal '+name+' = (function()\n'+(omni_gui.HERE/'modules'/(name+'.luau')).read_text(encoding='utf-8')+'\nend)()\n'
        code+='''
local maid = Maid.new(); local count = 0
maid:GiveTask(function() count += 1 end)
maid:GiveTask(function() error("expected cleanup fault") end)
local pending = coroutine.create(function() coroutine.yield() end); coroutine.resume(pending); maid:GiveTask(pending)
maid:Destroy(); maid:Destroy(); assert(count == 1 and coroutine.status(pending) == "dead" and warnings == 1)
maid:GiveTask(function() count += 1 end); assert(count == 2)
local signal = Signal.new(); local hits = 0
local c = signal:Connect(function(n) hits += n end); signal:Fire(2); c:Disconnect(); c:Disconnect(); signal:Fire(9); assert(hits == 2)
signal:Once(function() hits += 10; signal:Fire(0) end); signal:Fire(0); signal:Fire(0); assert(hits == 12)
local value = nil
local waiter = coroutine.create(function() value = signal:Wait() end); coroutine.resume(waiter); signal:Fire(42); assert(value == 42)
local cancelled = coroutine.create(function() signal:Wait() end); coroutine.resume(cancelled)
signal:Destroy(); assert(coroutine.status(cancelled) == "dead"); assert(not pcall(function() signal:Connect(function() end) end))
for _, damping in ipairs({0, 0.2, 1, 1.000001, 2, 20}) do
 local a = Spring.Spring.new(3, damping, 1); local b = Spring.Spring.new(3, damping, 1)
 a.target = 5; b.target = 5; a:Impulse(2); b:Impulse(2)
 assert(a:Update(0) == 1); a:Update(0.4)
 for _ = 1, 40 do b:Update(0.01) end
 assert(math.abs(a.position - b.position) < 0.00001, tostring(damping))
 assert(math.abs(a.velocity - b.velocity) < 0.00001, tostring(damping))
 assert(not pcall(function() a:Update(-1) end))
end
local settled = Spring.Spring.new(3, 1, 0); settled.target = 10; for _ = 1, 600 do settled:Update(1/60) end
assert(math.abs(settled.position - 10) < 0.000001)
print("PASS actual Luau lifecycle, cancellation, reentrant Once, waiter cleanup and analytic springs")
'''
        with tempfile.TemporaryDirectory() as temp:
            path=pathlib.Path(temp)/'omni-lifecycle.luau';path.write_text(code,encoding='utf-8')
            r=subprocess.run([executable,str(path)],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('PASS actual Luau',r.stdout)

if __name__=='__main__':unittest.main()
