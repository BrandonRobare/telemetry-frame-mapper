import { useEffect, useRef } from 'react'
import { deriveLogoMotion, logoRampColor } from '../../shared/pipeline/stages'
import type { StageKey, StageState } from '../../shared/pipeline/stages'
import { generateReconstructionField, heightAt, FIELD_RADIUS } from '../../shared/pipeline/reconstructionField'
import { useSettingsStore } from '../settings/settingsStore'

interface Props {
  stageStates: Record<StageKey, StageState>
  className?: string
}

const POINT_COUNT = 800
const SEED = 7

/* The 3D brand logo: a point cloud that performs the pipeline. Points scatter
   (Import/Review), converge as COLMAP solves (Align, with orbiting camera
   frustums), bloom into splats (Train), and resolve onto a terrain landform
   (View/Export). Colors track live pipeline state via deriveLogoMotion; failed
   flares brick. Reuses the proven three.js lifecycle from the previous hex-prism 3D hero
   — lazy import, earthy env, DPR cap, visibility-pause, full disposal,
   reduced-motion + WebGL fallback (the earthy backdrop behind the canvas remains
   the fallback). */

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}

export default function ReconstructionLogo3D({ stageStates, className }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const pointer = useRef({ x: 0, y: 0 })
  // Mount-time states for the one-shot build effect; live updates flow through
  // the [stageStates] effect below (so we never write a ref during render).
  const statesRef = useRef(stageStates)
  const applyRef = useRef<((s: Record<StageKey, StageState>) => void) | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const container = canvas?.parentElement
    if (!canvas || !container) return

    let raf = 0
    let disposed = false
    const reduce =
      window.matchMedia('(prefers-reduced-motion: reduce)').matches ||
      useSettingsStore.getState().reducedMotion
    const cleanup: Array<() => void> = []

    const field = generateReconstructionField(POINT_COUNT, SEED)

    import('three')
      .then((THREE) => {
        if (disposed) return
        let renderer: import('three').WebGLRenderer
        try {
          renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true })
        } catch {
          return
        }
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
        renderer.toneMapping = THREE.ACESFilmicToneMapping
        cleanup.push(() => renderer.dispose())

        const w = container.clientWidth || 1
        const h = container.clientHeight || 1
        renderer.setSize(w, h, false)

        const scene = new THREE.Scene()
        const camera = new THREE.PerspectiveCamera(40, w / h, 0.1, 100)
        camera.position.set(0, 0.2, 4.2)

        // earthy gradient env for reflections (no asset load)
        const envCanvas = document.createElement('canvas')
        envCanvas.width = 16
        envCanvas.height = 128
        const ectx = envCanvas.getContext('2d')!
        const grad = ectx.createLinearGradient(0, 0, 0, 128)
        grad.addColorStop(0, '#fffaf0')
        grad.addColorStop(0.5, '#d8c39e')
        grad.addColorStop(1, '#3a2a18')
        ectx.fillStyle = grad
        ectx.fillRect(0, 0, 16, 128)
        const envTex = new THREE.CanvasTexture(envCanvas)
        envTex.mapping = THREE.EquirectangularReflectionMapping
        const pmrem = new THREE.PMREMGenerator(renderer)
        const envRT = pmrem.fromEquirectangular(envTex)
        scene.environment = envRT.texture
        cleanup.push(() => {
          envTex.dispose()
          envRT.texture.dispose()
          pmrem.dispose()
        })

        const group = new THREE.Group()
        group.rotation.x = -0.3
        scene.add(group)

        // --- point cloud ---
        const geo = new THREE.BufferGeometry()
        const positions = new Float32Array(field.scatter) // start scattered
        const colors = new Float32Array(POINT_COUNT * 3)
        geo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
        geo.setAttribute('color', new THREE.BufferAttribute(colors, 3))

        // soft round sprite (white core → transparent edge); vertex colors tint it
        const sprCanvas = document.createElement('canvas')
        sprCanvas.width = sprCanvas.height = 64
        const sctx = sprCanvas.getContext('2d')!
        const sgrad = sctx.createRadialGradient(32, 32, 0, 32, 32, 32)
        sgrad.addColorStop(0, 'rgba(255,255,255,1)')
        sgrad.addColorStop(0.45, 'rgba(255,255,255,0.85)')
        sgrad.addColorStop(1, 'rgba(255,255,255,0)')
        sctx.fillStyle = sgrad
        sctx.fillRect(0, 0, 64, 64)
        const sprite = new THREE.CanvasTexture(sprCanvas)

        const pointsMat = new THREE.PointsMaterial({
          size: 0.08,
          map: sprite,
          vertexColors: true,
          transparent: true,
          depthWrite: false,
          sizeAttenuation: true,
        })
        const points = new THREE.Points(geo, pointsMat)
        group.add(points)
        cleanup.push(() => {
          geo.dispose()
          pointsMat.dispose()
          sprite.dispose()
        })

        // --- terrain landform (fades in with `solid`) ---
        const SEG = 24
        const SPAN = FIELD_RADIUS * 2
        const tv: number[] = []
        const ti: number[] = []
        for (let iz = 0; iz <= SEG; iz++) {
          for (let ix = 0; ix <= SEG; ix++) {
            const x = (ix / SEG - 0.5) * SPAN
            const z = (iz / SEG - 0.5) * SPAN
            tv.push(x, heightAt(x, z), z)
          }
        }
        for (let iz = 0; iz < SEG; iz++) {
          for (let ix = 0; ix < SEG; ix++) {
            const a = iz * (SEG + 1) + ix
            const b = a + 1
            const c = a + (SEG + 1)
            const d = c + 1
            ti.push(a, c, b, b, c, d)
          }
        }
        const terrGeo = new THREE.BufferGeometry()
        terrGeo.setAttribute('position', new THREE.Float32BufferAttribute(tv, 3))
        terrGeo.setIndex(ti)
        terrGeo.computeVertexNormals()
        const terrMat = new THREE.MeshPhysicalMaterial({
          color: 0xa8bba3,
          roughness: 0.55,
          metalness: 0,
          flatShading: true,
          transparent: true,
          opacity: 0,
          envMapIntensity: 0.8,
        })
        const terrain = new THREE.Mesh(terrGeo, terrMat)
        group.add(terrain)
        cleanup.push(() => {
          terrGeo.dispose()
          terrMat.dispose()
        })

        // --- orbiting camera frustums (peak during Align) ---
        const frustaGroup = new THREE.Group()
        const frustaMat = new THREE.LineBasicMaterial({ color: 0xc8902f, transparent: true, opacity: 0 })
        const fd = 0.32
        const fh = 0.16
        const fEdges = [
          0, 0, 0, fh, fh, fd,
          0, 0, 0, -fh, fh, fd,
          0, 0, 0, fh, -fh, fd,
          0, 0, 0, -fh, -fh, fd,
          fh, fh, fd, -fh, fh, fd,
          -fh, fh, fd, -fh, -fh, fd,
          -fh, -fh, fd, fh, -fh, fd,
          fh, -fh, fd, fh, fh, fd,
        ]
        for (let c = 0; c < 3; c++) {
          const fg = new THREE.BufferGeometry()
          fg.setAttribute('position', new THREE.Float32BufferAttribute(fEdges, 3))
          const seg = new THREE.LineSegments(fg, frustaMat)
          const ang = (c / 3) * Math.PI * 2
          seg.position.set(1.25 * Math.cos(ang), 0.5, 1.25 * Math.sin(ang))
          seg.lookAt(0, 0, 0)
          frustaGroup.add(seg)
          cleanup.push(() => fg.dispose())
        }
        group.add(frustaGroup)
        cleanup.push(() => frustaMat.dispose())

        // --- benchmark core ---
        const coreGeo = new THREE.SphereGeometry(0.07, 20, 20)
        const coreMat = new THREE.MeshStandardMaterial({ color: 0x9a5e32, roughness: 0.4 })
        group.add(new THREE.Mesh(coreGeo, coreMat))
        cleanup.push(() => {
          coreGeo.dispose()
          coreMat.dispose()
        })

        scene.add(new THREE.AmbientLight(0xffffff, 0.55))
        const key = new THREE.DirectionalLight(0xfff0d8, 1.4)
        key.position.set(3, 4, 5)
        scene.add(key)
        const fill = new THREE.DirectionalLight(0xb87c4c, 0.6)
        fill.position.set(-4, -2, -3)
        scene.add(fill)

        const tmpColor = new THREE.Color()
        let baseSize = 0.08
        let pulsing = false

        const apply = (states: Record<StageKey, StageState>) => {
          const m = deriveLogoMotion(states)
          const pos = geo.attributes.position.array as Float32Array
          for (let i = 0; i < POINT_COUNT; i++) {
            const j = i * 3
            pos[j] = lerp(field.scatter[j], field.target[j], m.organization)
            pos[j + 1] = lerp(field.scatter[j + 1], field.target[j + 1], m.organization)
            pos[j + 2] = lerp(field.scatter[j + 2], field.target[j + 2], m.organization)
          }
          geo.attributes.position.needsUpdate = true

          const col = geo.attributes.color.array as Float32Array
          for (let i = 0; i < POINT_COUNT; i++) {
            const o = Math.max(0, Math.min(1, m.organization + (field.tint[i] - 0.5) * 0.25))
            tmpColor.setStyle(m.failed ? '#b5503c' : logoRampColor(o))
            const j = i * 3
            col[j] = tmpColor.r
            col[j + 1] = tmpColor.g
            col[j + 2] = tmpColor.b
          }
          geo.attributes.color.needsUpdate = true

          baseSize = 0.05 + m.bloom * 0.06
          pointsMat.size = baseSize
          terrMat.opacity = m.solid * 0.9
          // frusta opacity peaks when organization is mid (the Align band)
          frustaMat.opacity = Math.max(0, 1 - Math.abs(m.organization - 0.5) / 0.32) * 0.6
          pulsing = m.activeIndex >= 0 && !m.failed
        }
        applyRef.current = apply
        apply(statesRef.current)
        cleanup.push(() => {
          applyRef.current = null
        })

        const ro = new ResizeObserver(() => {
          const nw = container.clientWidth || 1
          const nh = container.clientHeight || 1
          camera.aspect = nw / nh
          camera.updateProjectionMatrix()
          renderer.setSize(nw, nh, false)
        })
        ro.observe(container)
        cleanup.push(() => ro.disconnect())

        const render = () => renderer.render(scene, camera)
        let cx = 0
        let cy = 0
        let t = 0

        if (reduce) {
          render()
        } else {
          const loop = () => {
            if (disposed) return
            t += 0.016
            cx += (pointer.current.x * 0.6 - cx) * 0.06
            cy += (pointer.current.y * 0.4 - cy) * 0.06
            group.rotation.y = Math.sin(t * 0.4) * 0.4 + cx * 0.4
            group.rotation.x = -0.3 + cy
            frustaGroup.rotation.y = t * 0.5
            if (pulsing) pointsMat.size = baseSize * (1 + 0.16 * Math.sin(t * 3))
            render()
            raf = requestAnimationFrame(loop)
          }
          raf = requestAnimationFrame(loop)
          const onVis = () => {
            if (document.hidden) cancelAnimationFrame(raf)
            else raf = requestAnimationFrame(loop)
          }
          document.addEventListener('visibilitychange', onVis)
          cleanup.push(() => document.removeEventListener('visibilitychange', onVis))
        }
      })
      .catch(() => {})

    return () => {
      disposed = true
      cancelAnimationFrame(raf)
      cleanup.forEach((fn) => fn())
    }
  }, [])

  // Recolor/restate live when pipeline state changes (no rebuild).
  useEffect(() => {
    applyRef.current?.(stageStates)
  }, [stageStates])

  const onPointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    pointer.current = { x: (e.clientX - r.left) / r.width - 0.5, y: (e.clientY - r.top) / r.height - 0.5 }
  }

  return <canvas ref={canvasRef} onPointerMove={onPointerMove} className={className} aria-hidden="true" />
}
