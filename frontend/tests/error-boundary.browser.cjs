// Standalone browser harness tests the actual boundary with a React render failure.
// Button styling is stubbed; React and ErrorBoundary are loaded from the application.
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const repo=path.resolve(__dirname, '..');
const localRequire=createRequire(path.join(repo,'package.json'));
const ts=localRequire('typescript');
const modules=[], ids=new Map();
const boundaryFile=path.join(repo,'src/features/workspace/error-boundary.tsx');

function bundle(file) {
  if(ids.has(file))return ids.get(file);
  const id=modules.length;ids.set(file,id);modules.push(null);
  let code=file==='@button' ? `const React=require('react');exports.Button=({children,onClick})=>React.createElement('button',{onClick},children);` : fs.readFileSync(file,'utf8');
  if(file.endsWith('.tsx'))code=ts.transpileModule(code,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2020}}).outputText;
  code=code.replace(/require\(['"]([^'"]+)['"]\)/g,(match,specifier)=>{
    const target=specifier==='@/components/ui/button'?'@button':createRequire(file==='@button'?path.join(repo,'package.json'):file).resolve(specifier);
    return `require(${bundle(target)})`;
  });
  modules[id]=`function(module,exports,require){${code}\n}`;
  return id;
}
const boundary=bundle(boundaryFile),react=bundle(localRequire.resolve('react')),client=bundle(localRequire.resolve('react-dom/client'));
const script=`(()=>{const process={env:{NODE_ENV:'production'}};const modules=[${modules.join(',')}],cache={};function require(id){if(cache[id])return cache[id].exports;const module=cache[id]={exports:{}};modules[id](module,module.exports,require);return module.exports;}const React=require(${react});const {ErrorBoundary}=require(${boundary});const {createRoot}=require(${client});function Thrower(){const [fail,setFail]=React.useState(false);if(fail)throw new Error('Intentional acceptance-test render error');return React.createElement('button',{onClick:()=>setFail(true)},'Trigger render error');}createRoot(document.getElementById('root')).render(React.createElement(ErrorBoundary,null,React.createElement(Thrower)));})();`;

(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{})});
  try {
    const page=await browser.newPage();
    await page.setContent('<p id="outside">Workspace shell stays available</p><div id="root"></div>');
    await page.addScriptTag({content:script});
    await page.getByRole('button',{name:'Trigger render error'}).click();
    await page.getByRole('heading',{name:'Không thể hiển thị nội dung'}).waitFor();
    assert.ok(await page.locator('#outside').isVisible());
    await page.getByRole('button',{name:'Thử lại',exact:true}).click();
    await page.getByRole('button',{name:'Trigger render error'}).waitFor();
    assert.equal(await page.getByRole('alert').count(),0);
    console.log('PASS: real React rendering failure is caught by the actual ErrorBoundary; retry remounts the child successfully.');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
