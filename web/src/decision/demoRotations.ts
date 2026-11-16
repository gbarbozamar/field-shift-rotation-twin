import rawDemoRotations from '../data/demo_rotations_d128.json'
import { parseRotationDefinition } from '../seam/rotationDefinition'
import type { RotationDefinitionExample } from '../seam/rotationDefinition'

/**
 * The two rotations of the demonstration (D128) that the decision section
 * sends to the decision route for example-field-1 (issue #354). The file
 * web/src/data/demo_rotations_d128.json was added at the request of the
 * orchestrating session (D161), citing D128 and D72: soybean with winter
 * fallow, and wheat, second-crop soybean, then maize, on PLACEHOLDER years
 * with the month and day of row USER-AP (D72), scenario dates, not observed
 * harvests. They are the pair DEMO_ROTATIONS of api/test_runner_residues.py;
 * web/test_demo_rotations_d128.py checks them against the rotation
 * definition contract, that pair, row USER-AP and the crops of the
 * parameter catalogue.
 *
 * Each item is read by the parser of the run seam (ids, label, the whole
 * document kept unchanged for the request). Pure: value in, definitions out,
 * or an Error naming what is wrong.
 */
export function parseDemoRotations(value: unknown): RotationDefinitionExample[] {
  if (!Array.isArray(value)) {
    throw new Error('invalid-demo-rotations:not-a-list')
  }
  return value.map((item) => parseRotationDefinition(item))
}

/** The two rotation definitions of D128, as the interface holds them. */
export const demoRotationsD128: RotationDefinitionExample[] = parseDemoRotations(rawDemoRotations)
