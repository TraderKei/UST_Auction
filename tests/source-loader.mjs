import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import ts from "typescript";

const require = createRequire(import.meta.url);
for (const extension of [".ts", ".tsx"]) {
  require.extensions[extension] = (module, filename) => {
    const result = ts.transpileModule(readFileSync(filename, "utf8"), {
      compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    });
    module._compile(result.outputText, filename);
  };
}
export const loadSource = path => require(path);
