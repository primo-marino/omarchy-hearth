import test from 'node:test';
import assert from 'node:assert/strict';
import { load } from './load.mjs';

const MenuSync = load('MenuSync');

test('shQuote quotes spaces and single quotes', () => {
  assert.equal(MenuSync.shQuote("/tmp/my hearth's cli"), "'/tmp/my hearth'\\''s cli'");
});

test('build returns disconnected tree when no instances', () => {
  const tree = MenuSync.build({ instances: [] }, {}, [], '/tmp/hearth', false);
  assert.equal(tree['hearth.open'].action, 'omarchy-shell shell summon io.github.primo-marino.hearth');
  assert.ok(tree['hearth.status']);
});

test('build marks disconnected when instances exist but not connected', () => {
  const config = { activeInstanceId: 'home', instances: [{ id: 'home', name: 'Home' }] };
  const tree = MenuSync.build(config, {}, [], '/tmp/hearth', false);
  assert.equal(tree['hearth.status'].label, 'Hearth is not connected');
});

test('entity leaf action uses cli act entity_id', () => {
  const config = { activeInstanceId: 'home', instances: [{ id: 'home', name: 'Home' }] };
  const rooms = [
    {
      area_id: 'kitchen',
      name: 'Kitchen',
      entities: [{ entity_id: 'light.kitchen', name: 'Kitchen light', kind: 'toggle' }],
    },
  ];
  const tree = MenuSync.build(config, {}, rooms, '/tmp/hearth', true);
  assert.equal(tree['hearth.rooms.kitchen.light_kitchen'].action, "'/tmp/hearth' act 'light.kitchen'");
});

test('room overflow uses open --room', () => {
  const config = { activeInstanceId: 'home', instances: [{ id: 'home', name: 'Home' }] };
  const entities = [];
  for (let i = 0; i < 41; i++) {
    entities.push({ entity_id: `light.k${i}`, name: `Light ${i}`, kind: 'toggle' });
  }
  const rooms = [{ area_id: 'kitchen', name: 'Kitchen', entities }];
  const tree = MenuSync.build(config, {}, rooms, '/tmp/hearth', true);
  assert.equal(tree['hearth.rooms.kitchen.more'].action, "'/tmp/hearth' open --room 'kitchen'");
});
