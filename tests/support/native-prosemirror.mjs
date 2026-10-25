// Optional native-editor fixture. Bundle with esbuild and the official
// prosemirror-state/view/schema-basic packages, then set MS_NATIVE_EDITOR_BUNDLE.
import {EditorState, Plugin} from 'prosemirror-state';
import {EditorView, Decoration, DecorationSet} from 'prosemirror-view';
import {schema} from 'prosemirror-schema-basic';
window.createNativeComposer = ({exposeView=true,decorated=true,mount=document.querySelector('#mount')}={}) => {
  window.nativeTransactions=0;window.rejectNative=false;window.throwAfterNative=false;
  const plugin=new Plugin({props:{decorations(state){
    return decorated ? DecorationSet.create(state.doc,[Decoration.widget(1,()=>{
      const hint=document.createElement('span');hint.className='ProseMirror-widget';
      hint.contentEditable='false';hint.textContent='Native editor hint';return hint;
    },{side:-1})]) : null;
  }}});
  window.pm=new EditorView(mount,{
    state:EditorState.create({schema,plugins:[plugin]}),
    dispatchTransaction(transaction){
      nativeTransactions++;
      if(!rejectNative)pm.updateState(pm.state.apply(transaction));
      if(throwAfterNative)throw Error('Fixture plugin failed after accepting the edit');
    }
  });
  pm.dom.id='prompt-textarea';
  if(exposeView)pm.dom.editor={get view(){return pm;}};
  window.nativeText=()=>pm.state.doc.textBetween(0,pm.state.doc.content.size,'\n','\n');
};
