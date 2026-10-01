// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { ViewerToolbar } from './SplatViewerTab'
import { NO_SURFACE_SAMPLER_REASON, surfaceMeasurementGate } from './measurementMath'
import type { GeoTransform } from '../../types/api'

const GEO: GeoTransform = {
  scale: 1,
  rotation: [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
  translation: [0, 0, 0],
  utm_zone: '17N',
  utm_origin: [500000, 3900000],
}

afterEach(() => {
  cleanup()
})

function renderToolbar(surfaceToolsUnavailableReason: string | null) {
  const onToolChange = vi.fn()
  render(
    <ViewerToolbar
      activeTool="none"
      onToolChange={onToolChange}
      geoTransformAvailable
      hasMeasurePoints={false}
      onClearMeasure={() => {}}
      surfaceToolsUnavailableReason={surfaceToolsUnavailableReason}
    />,
  )
  return { onToolChange }
}

function button(name: RegExp): HTMLButtonElement {
  return screen.getByRole('button', { name }) as HTMLButtonElement
}

// #953: profile and cut/fill volume used to sample a constant flat plane. Until
// the viewer has a real surface sampler they must not be startable at all.
describe('ViewerToolbar surface-measurement gate', () => {
  it('disables profile and volume and says why when there is no surface sampler', () => {
    const gate = surfaceMeasurementGate(null, GEO)
    const { onToolChange } = renderToolbar(gate.available ? null : gate.reason)

    for (const name of [/Profile/, /Volume/]) {
      const tool = button(name)
      expect(tool.disabled).toBe(true)
      expect(tool.title).toBe(NO_SURFACE_SAMPLER_REASON)
      fireEvent.click(tool)
    }
    expect(onToolChange).not.toHaveBeenCalled()
    expect(screen.getByText(NO_SURFACE_SAMPLER_REASON)).toBeTruthy()
  })

  it('leaves distance and area measurement available', () => {
    const { onToolChange } = renderToolbar(NO_SURFACE_SAMPLER_REASON)

    expect(button(/Distance/).disabled).toBe(false)
    expect(button(/Area/).disabled).toBe(false)
    fireEvent.click(button(/Distance/))
    expect(onToolChange).toHaveBeenCalledWith('measure-dist')
  })

  it('enables profile and volume once a surface sampler is available', () => {
    const gate = surfaceMeasurementGate(() => 10, GEO)
    const { onToolChange } = renderToolbar(gate.available ? null : gate.reason)

    expect(button(/Profile/).disabled).toBe(false)
    expect(button(/Volume/).disabled).toBe(false)
    expect(screen.queryByText(NO_SURFACE_SAMPLER_REASON)).toBeNull()
    fireEvent.click(button(/Volume/))
    expect(onToolChange).toHaveBeenCalledWith('measure-volume')
  })
})
