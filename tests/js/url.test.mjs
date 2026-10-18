import test from 'node:test';
import assert from 'node:assert/strict';
import { load } from './load.mjs';

const Url = load('Url');

test('bare host defaults to http and 8123', () => {
  const r = Url.parse('homeassistant.local');
  assert.equal(r.ok, true);
  assert.equal(r.origin, 'http://homeassistant.local:8123');
  assert.equal(r.scheme, 'http');
  assert.equal(r.port, 8123);
  assert.equal(r.plaintextHttp, true);
});

test('https default port 443 is omitted from origin', () => {
  const r = Url.parse('https://ha.example');
  assert.equal(r.ok, true);
  assert.equal(r.origin, 'https://ha.example');
  assert.equal(r.port, 443);
  assert.equal(r.scheme, 'https');
});

test('explicit port is kept', () => {
  const r = Url.parse('https://ha.example:8443');
  assert.equal(r.ok, true);
  assert.equal(r.origin, 'https://ha.example:8443');
  assert.equal(r.port, 8443);
});

test('IPv6 in brackets with port', () => {
  const r = Url.parse('[fd12::1]:8123');
  assert.equal(r.ok, true);
  assert.equal(r.host, 'fd12::1');
  assert.equal(r.port, 8123);
  assert.equal(r.origin, 'http://[fd12::1]:8123');
});

test('unbracketed IPv6 is rejected', () => {
  const r = Url.parse('fd12::1');
  assert.equal(r.ok, false);
  assert.equal(r.error, 'IPv6 addresses need brackets, e.g. [fd12::1]:8123.');
});

test('bad scheme is rejected', () => {
  const r = Url.parse('ftp://ha.example');
  assert.equal(r.ok, false);
  assert.equal(r.error, 'Use http or https.');
});

test('spaces are rejected', () => {
  const r = Url.parse('ha example');
  assert.equal(r.ok, false);
  assert.equal(r.error, 'URL cannot contain spaces.');
});

test('port out of range is rejected', () => {
  const r = Url.parse('ha.example:70000');
  assert.equal(r.ok, false);
  assert.equal(r.error, 'Port must be between 1 and 65535.');
});

test('nabu casa sets hideTlsInsecure', () => {
  const r = Url.parse('https://abc.ui.nabu.casa');
  assert.equal(r.ok, true);
  assert.equal(r.nabuCasa, true);
  assert.equal(r.hideTlsInsecure, true);
});

test('trailing slash is allowed', () => {
  const r = Url.parse('https://ha.example/');
  assert.equal(r.ok, true);
  assert.equal(r.origin, 'https://ha.example');
});

test('subpath is rejected', () => {
  for (const input of ['https://gw.example/ha/', 'host:8123/x', 'host?x=1', 'host#frag']) {
    const r = Url.parse(input);
    assert.equal(r.ok, false, input);
    assert.equal(
      r.error,
      'Home Assistant on a URL subpath is not supported. Enter just the address, e.g. https://gw.example',
      input
    );
  }
});

test('slug and uniqueInstanceId', () => {
  assert.equal(Url.slug('My Home!'), 'my-home');
  assert.equal(Url.slug(''), 'home');
  assert.equal(Url.uniqueInstanceId('home', ['home', 'home-2']), 'home-3');
});
