import test from 'node:test';
import assert from 'node:assert/strict';
import { load } from './load.mjs';

const Config = load('Config');

test('loadConfig accepts version 1 and missing version', () => {
  const v1 = Config.loadConfig('{"version":1,"instances":[]}');
  assert.equal(v1.ok, true);
  assert.equal(v1.config.version, 1);
  const missing = Config.loadConfig('{"instances":[]}');
  assert.equal(missing.ok, true);
  assert.equal(missing.config.version, 1);
});

test('loadConfig rejects version 2', () => {
  const r = Config.loadConfig('{"version":2,"instances":[]}');
  assert.equal(r.ok, false);
  assert.match(r.error, /newer/);
});

test('loadConfig handles bad JSON', () => {
  const r = Config.loadConfig('{bad');
  assert.equal(r.ok, false);
  assert.equal(r.error, 'Hearth config is not valid JSON.');
});

test('loadState accepts version 1 and missing version', () => {
  const v1 = Config.loadState('{"version":1,"instances":{}}');
  assert.equal(v1.ok, true);
  assert.equal(v1.state.version, 1);
  const missing = Config.loadState('{"instances":{}}');
  assert.equal(missing.ok, true);
  assert.equal(missing.state.version, 1);
});

test('loadState rejects version 2', () => {
  const r = Config.loadState('{"version":2,"instances":{}}');
  assert.equal(r.ok, false);
  assert.match(r.error, /newer/);
});

test('loadState handles bad JSON', () => {
  const r = Config.loadState('{bad');
  assert.equal(r.ok, false);
  assert.equal(r.error, 'Hearth state is not valid JSON.');
});

test('setActiveInstance preserves instances and sets active id', () => {
  const cfg = { version: 1, activeInstanceId: 'a', instances: [{ id: 'a' }, { id: 'b' }] };
  const next = Config.setActiveInstance(cfg, 'b');
  assert.equal(next.activeInstanceId, 'b');
  assert.equal(next.instances.length, 2);
  assert.equal(next.instances[1].id, 'b');
});

test('upsertInstance and findInstance', () => {
  const cfg = Config.emptyConfig();
  const next = Config.upsertInstance(cfg, { id: 'home', name: 'Home' });
  assert.equal(next.activeInstanceId, 'home');
  assert.equal(next.instances.length, 1);
  assert.equal(Config.findInstance(next, 'home').name, 'Home');
  const updated = Config.upsertInstance(next, { id: 'home', name: 'House' });
  assert.equal(updated.instances.length, 1);
  assert.equal(Config.findInstance(updated, 'home').name, 'House');
});

test('toggleFavorite toggles on and off', () => {
  const state = Config.emptyState();
  const on = Config.toggleFavorite(state, 'home', 'light.kitchen');
  assert.equal(on.starred, true);
  assert.deepEqual(Array.from(on.favorites), ['light.kitchen']);
  const off = Config.toggleFavorite(on.state, 'home', 'light.kitchen');
  assert.equal(off.starred, false);
  assert.deepEqual(Array.from(off.favorites), []);
});

test('instanceState returns arrays', () => {
  const state = Config.emptyState();
  const inst = Config.instanceState(state, 'home');
  assert.deepEqual(Array.from(inst.favorites), []);
  assert.deepEqual(Array.from(inst.recents), []);
});
