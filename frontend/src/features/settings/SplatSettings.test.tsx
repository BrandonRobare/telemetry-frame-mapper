// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import SplatSettings from './SplatSettings'
import type { AppSettings } from './api'

// #820: Metal's `quick` preset runs at 1,250 iterations by accelerator policy
// (CUDA stays at 1,000) whenever config.yaml omits the field. GET /settings
// now reports that resolved value instead of the bare cross-platform default.
const settingsFixture: AppSettings = {
  general: {
    default_basemap: 'esri_satellite',
    target_crs: 'EPSG:32617',
    imports_dir: './imports',
    processed_dir: './processed',
    exports_dir: './exports',
    data_dir: './data',
  },
  mission: {
    altitude_ft: 200,
    fov_horizontal_deg: 83,
    fov_vertical_deg: 53,
    image_width_px: 4000,
    image_height_px: 3000,
    desired_side_overlap: 0.7,
    desired_forward_overlap: 0.8,
    lane_spacing_ft: 105,
    default_video_fps: 2,
    battery_range_m: 3000,
    mission_buffer_pct: 0.1,
    flight_log_match_tolerance_sec: 2,
  },
  ingest: {
    thumbnail_size_px: 200,
    thumbnail_jpeg_quality: 75,
    accepted_extensions: ['.jpg'],
    blur_threshold: 100,
    dark_threshold: 50,
    bright_threshold: 210,
    filter_zero_gps: true,
  },
  reconstruction: {
    default_preset: 'quick',
    colmap_threads: 8,
    sift_max_features: 8192,
    matcher: 'exhaustive',
    camera_model: 'PINHOLE',
    presets: {
      quick: { iterations: 1250, max_gaussians: 350000, sh_degree: 1, downscale_factor: 4 },
      full: { iterations: 30000, max_gaussians: 1000000, sh_degree: 2, downscale_factor: 2 },
    },
  },
  render: {
    flythrough_fps: 30,
    flythrough_width: 1920,
    flythrough_height: 1080,
    thumbnail_size_px: 512,
    thumbnail_quality: 85,
    lod_preview_ratio: 0.1,
    lod_medium_ratio: 0.5,
  },
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

function renderSplatSettings() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <SplatSettings />
    </QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('SplatSettings save payload', () => {
  it('sends only the preset field the operator touched, not the untouched Metal-policy iterations', async () => {
    let patchBody: unknown = null
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url === '/settings' && (!init || init.method === undefined)) {
          return jsonResponse(settingsFixture)
        }
        if (url === '/settings' && init?.method === 'PATCH') {
          patchBody = JSON.parse(String(init.body))
          return jsonResponse(settingsFixture)
        }
        throw new Error(`Unexpected request: ${url} ${init?.method ?? 'GET'}`)
      }),
    )

    renderSplatSettings()

    // Open the `quick` preset's Advanced section (its own toggle is first in
    // document order) and edit max_gaussians only — `quick.iterations`
    // (1,250, the Metal-policy-derived value) is never touched.
    await screen.findByText('quick preset')
    fireEvent.click(screen.getAllByRole('button', { name: 'Advanced' })[0])
    const maxGaussiansInput = await screen.findByDisplayValue('350000')
    fireEvent.change(maxGaussiansInput, { target: { value: '400000' } })

    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(patchBody).not.toBeNull())
    expect(patchBody).toEqual({
      reconstruction: { presets: { quick: { max_gaussians: 400000 } } },
    })
  })
})
