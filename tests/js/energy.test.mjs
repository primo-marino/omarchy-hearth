import test from 'node:test';
import assert from 'node:assert/strict';
import { load } from './load.mjs';

const Energy = load('Energy');

test('formatKwh', () => {
  assert.equal(Energy.formatKwh(12.34), '12.3 kWh');
  assert.equal(Energy.formatKwh(1.234), '1.2 kWh');
  assert.equal(Energy.formatKwh(0.1234), '0.12 kWh');
  assert.equal(Energy.formatKwh(null), '');
});

test('toWatts converts kW and MW', () => {
  assert.equal(Energy.toWatts('1.5', { unit_of_measurement: 'kW' }), 1500);
  assert.equal(Energy.toWatts('0.5', { unit_of_measurement: 'MW' }), 500000);
  assert.equal(Energy.toWatts('350', {}), 350);
});

test('formatPower', () => {
  assert.equal(Energy.formatPower(1500), '1.5 kW');
  assert.equal(Energy.formatPower(350), '350 W');
  assert.equal(Energy.formatPower(0), '');
});

test('fromHelper hides disabled data', () => {
  const off = Energy.fromHelper({ enabled: false, reason: 'no_statistics' });
  assert.equal(off.enabled, false);
  assert.equal(off.reason, 'no_statistics');
});

test('isPowerEntity', () => {
  assert.equal(Energy.isPowerEntity({ powerIds: ['sensor.solar_power'] }, 'sensor.solar_power'), true);
  assert.equal(Energy.isPowerEntity({ powerIds: [] }, 'sensor.solar_power'), false);
});
