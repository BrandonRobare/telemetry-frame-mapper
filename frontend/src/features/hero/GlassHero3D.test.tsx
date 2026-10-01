// level: component; area: reconstruction-splat
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import GlassHero3D from './GlassHero3D'

// The canvas animation needs WebGL; render the actual hero, pipeline, and action.
vi.mock('./ReconstructionLogo3D', () => ({ default: () => null }))
afterEach(cleanup)

it('shows the import stage and opens the import action', async () => {
  const onImport = vi.fn()
  render(<GlassHero3D onImport={onImport} />)
  expect(screen.getByRole('button', { name: /^Import —/ })).toBeTruthy()
  await userEvent.click(screen.getByRole('button', { name: 'Import a flight' }))
  expect(onImport).toHaveBeenCalledTimes(1)
  expect(screen.getByText('.jpg frames in a folder')).toBeTruthy()
})
