import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const JS_DIR = new URL('../../js/', import.meta.url);

export function load(name) {
  const file = new URL(`${name}.js`, JS_DIR);
  const source = readFileSync(file, 'utf8').replace(/^\.pragma library\r?\n/, '');
  const context = {};
  runInNewContext(source, context, { filename: file.pathname });
  return context;
}
