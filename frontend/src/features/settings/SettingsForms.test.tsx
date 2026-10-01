// level: component; area: platform-ops
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import GeneralSettings from './GeneralSettings'
import MissionPlanningSettings from './MissionPlanningSettings'
import ReconstructionSettings from './ReconstructionSettings'
import RenderExportSettings from './RenderExportSettings'
import SplatSettings from './SplatSettings'
import { jsonResponse, mockApi, renderWithQuery } from '../../test/api'
import { settingsFixture } from '../../test/settings'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it.each([
  { name: 'General', Component: GeneralSettings, current: 'EPSG:32617', invalid: 'invalid', error: 'Target CRS must look like EPSG:32617', advanced: false },
  { name: 'Mission', Component: MissionPlanningSettings, current: '0.7', invalid: '2', error: 'Side overlap must be at most 1', advanced: false },
  { name: 'Reconstruction', Component: ReconstructionSettings, current: '8', invalid: '0', error: 'COLMAP threads must be greater than 0', advanced: true },
  { name: 'Render', Component: RenderExportSettings, current: '30', invalid: '100', error: 'Flythrough FPS must be at most 60', advanced: false },
  { name: 'Splat', Component: SplatSettings, current: '1250', invalid: '0', error: 'Iterations must be greater than 0', advanced: false },
])('$name shows a validation error and blocks PATCH for invalid input', async ({ Component, current, invalid, error, advanced }) => {
  const fetchMock = mockApi(() => jsonResponse(settingsFixture))
  renderWithQuery(<Component />)
  if (advanced) await userEvent.click(screen.getByRole('button', { name: 'Advanced' }))
  const input = await screen.findByDisplayValue(current)
  await userEvent.clear(input)
  await userEvent.type(input, invalid)
  expect(screen.getByText(error)).toBeTruthy()
  const save = screen.getByRole('button', { name: 'Save changes' })
  expect((save as HTMLButtonElement).disabled).toBe(true)
  await userEvent.click(save)
  expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'PATCH')).toBe(false)
})
