import { describe, expect, it } from 'vitest'

import {
  normalizeSparkiiOpenString,
  pathFromSparkiiDeepLink,
  pathFromOpenDeepLink,
  resolveSparkiiOpenPath
} from './sparkii-open-target'

describe('normalizeSparkiiOpenString', () => {
  it('accepts hash-router paths and strips a leading hash', () => {
    expect(normalizeSparkiiOpenString('/index-network/intent/1')).toBe('/index-network/intent/1')
    expect(normalizeSparkiiOpenString('#/index-network/intent/1')).toBe('/index-network/intent/1')
  })

  it('maps plugin-scoped sparkii:// deep links to the same path', () => {
    expect(normalizeSparkiiOpenString('sparkii://index-network/intent/1')).toBe('/index-network/intent/1')
    expect(normalizeSparkiiOpenString('sparkii://index-network/intent/1?focus=true')).toBe(
      '/index-network/intent/1?focus=true'
    )
  })

  it('maps sparkii://open/… deep links by stripping the open host', () => {
    expect(normalizeSparkiiOpenString('sparkii://open/index-network/intent/1')).toBe('/index-network/intent/1')
    expect(normalizeSparkiiOpenString('sparkii://open/settings/plugins')).toBe('/settings/plugins')
  })

  it('rejects reserved sparkii kinds and unsafe paths', () => {
    expect(normalizeSparkiiOpenString('sparkii://blueprint/morning-brief')).toBeNull()
    expect(normalizeSparkiiOpenString('sparkii://plugin/install')).toBeNull()
    expect(normalizeSparkiiOpenString('https://example.com/x')).toBeNull()
    expect(normalizeSparkiiOpenString('/../etc/passwd')).toBeNull()
    expect(normalizeSparkiiOpenString('index-network')).toBeNull()
  })
})

describe('resolveSparkiiOpenPath', () => {
  it('merges structured path + params', () => {
    expect(resolveSparkiiOpenPath({ path: '/index-network/intent/1', params: { focus: 'true' } })).toBe(
      '/index-network/intent/1?focus=true'
    )
  })

  it('resolves href the same as a bare string', () => {
    expect(resolveSparkiiOpenPath({ href: 'sparkii://index-network/intent/1' })).toBe('/index-network/intent/1')
  })
})

describe('pathFromSparkiiDeepLink', () => {
  it('builds the navigate path from a plugin-scoped deep-link payload', () => {
    expect(pathFromSparkiiDeepLink('index-network', 'intent/1')).toBe('/index-network/intent/1')
  })

  it('builds the navigate path from sparkii://open/… payloads', () => {
    expect(pathFromOpenDeepLink('index-network/intent/1')).toBe('/index-network/intent/1')
    expect(pathFromSparkiiDeepLink('open', 'agent/42')).toBe('/agent/42')
  })

  it('ignores reserved kinds', () => {
    expect(pathFromSparkiiDeepLink('blueprint', 'morning-brief')).toBeNull()
    expect(pathFromSparkiiDeepLink('plugin', 'install')).toBeNull()
  })
})
