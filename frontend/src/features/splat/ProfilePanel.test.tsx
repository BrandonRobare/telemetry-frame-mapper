// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import ProfilePanel from './ProfilePanel'
import type { ProfileSample } from './measurementMath'

const samples: ProfileSample[] = [
  { distance_m: 0, x: 0, z: 0, elevation: 10, lat: 40, lon: -105 },
  { distance_m: 5, x: 5, z: 0, elevation: 14, lat: 40.0001, lon: -105 },
  { distance_m: 10, x: 10, z: 0, elevation: 8, lat: 40.0002, lon: -105 },
]

afterEach(() => {
  cleanup()
  document.documentElement.style.removeProperty('--accent-strong')
  document.documentElement.style.removeProperty('--text-muted')
  document.documentElement.style.removeProperty('--border')
  document.documentElement.style.removeProperty('--bg')
  vi.restoreAllMocks()
})

function clickSvgDownloadAndCaptureAnchor(): HTMLAnchorElement {
  const anchors: HTMLAnchorElement[] = []
  const realCreateElement = document.createElement.bind(document)
  vi.spyOn(document, 'createElement').mockImplementation((tagName: string) => {
    const el = realCreateElement(tagName)
    if (tagName === 'a') anchors.push(el as HTMLAnchorElement)
    return el
  })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

  fireEvent.click(screen.getByTitle('Download SVG chart'))

  const svgAnchor = anchors.find((a) => a.download === 'elevation_profile.svg')
  if (!svgAnchor) throw new Error('SVG export anchor was not created')
  return svgAnchor
}

describe('ProfilePanel SVG export', () => {
  it('resolves every CSS custom property to a concrete value before serializing', () => {
    // Mirrors real index.css tokens so the resolved colors are checkable.
    document.documentElement.style.setProperty('--accent-strong', '#9A5E32')
    document.documentElement.style.setProperty('--text-muted', '#6B6456')
    document.documentElement.style.setProperty('--border', '#E4D8C2')
    document.documentElement.style.setProperty('--bg', '#F7F1DE')

    render(<ProfilePanel samples={samples} onClear={() => {}} />)

    const anchor = clickSvgDownloadAndCaptureAnchor()
    const svgString = decodeURIComponent(
      anchor.href.replace('data:image/svg+xml;charset=utf-8,', ''),
    )

    expect(svgString).not.toContain('var(--')
    // Profile polyline keeps a concrete stroke color, not just "not var(...)".
    expect(svgString).toMatch(/<polyline[^>]*stroke="#9A5E32"/)
  })

  it('leaves the on-screen chart theme-reactive (still using CSS variables)', () => {
    render(<ProfilePanel samples={samples} onClear={() => {}} />)

    const liveSvg = document.getElementById('elevation-profile-svg')
    expect(liveSvg?.innerHTML).toContain('var(--accent-strong)')
  })
})
