import test from 'node:test';
import assert from 'node:assert/strict';
import { searchLotes } from './lotesService.ts';
test('usa pesquisa local quando Algolia está indisponível', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => { throw new Error('offline'); };
  const result = await searchLotes([{ titulo: 'Trator agrícola', uf: 'GO' }, { titulo: 'Automóvel', uf: 'SP' }], 'trator');
  globalThis.fetch = original;
  assert.equal(result.length, 1); assert.match(result[0].titulo ?? '', /Trator/);
});
