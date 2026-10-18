import test from 'node:test';
import assert from 'node:assert/strict';
import { load } from './load.mjs';

const Entities = load('Entities');

test('primaryService for toggle, fan, button, lock, cover, climate', () => {
  assert.equal(Entities.primaryService('light', 'toggle', 'on'), 'toggle');
  assert.equal(Entities.primaryService('fan', 'fan', 'on'), 'toggle');
  assert.equal(Entities.primaryService('button', 'activate', ''), 'press');
  assert.equal(Entities.primaryService('input_button', 'activate', ''), 'press');
  assert.equal(Entities.primaryService('lock', 'lock', 'unlocked'), 'lock');
  assert.equal(Entities.primaryService('lock', 'lock', 'locked'), 'unlock');
  assert.equal(Entities.primaryService('cover', 'cover', 'open'), 'close_cover');
  assert.equal(Entities.primaryService('cover', 'cover', 'closed'), 'open_cover');
  assert.equal(Entities.primaryService('climate', 'climate', 'heat'), 'set_temperature');
});

test('validEntityId', () => {
  assert.equal(Entities.validEntityId('light.kitchen'), true);
  assert.equal(Entities.validEntityId('Light.Kitchen'), false);
  assert.equal(Entities.validEntityId('light'), false);
  assert.equal(Entities.validEntityId('light.kitchen;rm'), false);
});

test('domainOf and kindOf', () => {
  assert.equal(Entities.domainOf('light.kitchen'), 'light');
  assert.equal(Entities.domainOf(''), '');
  assert.equal(Entities.kindOf('light'), 'toggle');
  assert.equal(Entities.kindOf('fan'), 'fan');
  assert.equal(Entities.kindOf('button'), 'activate');
  assert.equal(Entities.kindOf('cover'), 'cover');
  assert.equal(Entities.kindOf('climate'), 'climate');
});

test('fanHasSpeeds respects supported_features bit 1', () => {
  assert.equal(Entities.fanHasSpeeds({}), true);
  assert.equal(Entities.fanHasSpeeds({ supported_features: 1 }), true);
  assert.equal(Entities.fanHasSpeeds({ supported_features: 2 }), false);
});

test('fan speed round trip for percentage_step 33.33', () => {
  const attrs = { percentage_step: 33.33 };
  const n = Entities.fanSpeedCount(attrs);
  assert.equal(n, 3);
  for (let i = 1; i <= n; i++) {
    const pct = Entities.fanPercentageForIndex(i, attrs);
    assert.equal(Entities.fanSpeedIndex('on', { percentage: pct, percentage_step: 33.33 }), i);
  }
});

test('fan speed round trip for percentage_step 25', () => {
  const attrs = { percentage_step: 25 };
  const n = Entities.fanSpeedCount(attrs);
  assert.equal(n, 4);
  for (let i = 1; i <= n; i++) {
    const pct = Entities.fanPercentageForIndex(i, attrs);
    assert.equal(Entities.fanSpeedIndex('on', { percentage: pct, percentage_step: 25 }), i);
  }
});

test('fanSpeedIndex off is zero', () => {
  assert.equal(Entities.fanSpeedIndex('off', { percentage: 100, percentage_step: 25 }), 0);
});
