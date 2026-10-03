import { readFile, writeFile } from 'node:fs/promises'
import openapiTS, { astToString } from 'openapi-typescript'

const schema = JSON.parse(await readFile(new URL('../../openapi.json', import.meta.url), 'utf8'))
const output = new URL('../../src/types/api.generated.ts', import.meta.url)
const generated = astToString(await openapiTS(schema, { alphabetize: true, defaultNonNullable: false }))
if (process.argv.includes('--check')) {
  if (await readFile(output, 'utf8') !== generated) {
    console.error('Generated API types drift: run npm run api:generate')
    process.exitCode = 1
  }
} else {
  await writeFile(output, generated)
}
