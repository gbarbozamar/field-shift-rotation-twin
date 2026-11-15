import rawRotation from '../data/rotation_definition.json'

/**
 * The rotation definition of the seam: the accepted contract example, copied
 * unchanged from contracts/rotation_definition/examples/ into web/src/data/
 * (issue #119). It is the one rotation the interface can ask the platform
 * route to run: the route takes the item exactly as the contract defines it,
 * so the whole document travels in the request, unedited (see the route's own
 * test, which sends this same example whole).
 *
 * The parser below reads only what the seam needs beside the request itself:
 * the ids that decide whether the example rotation belongs to the selected
 * field, and the label that names the run on screen. Pure: value in, typed
 * definition out, or an Error naming what is wrong. The errors are technical
 * codes without wording; nothing user-visible lives here.
 */

/** The example rotation definition, reduced to what the seam reads of it. */
export interface RotationDefinitionExample {
  case_id: string
  field_id: string
  rotation_id: string
  label: string
  /** The whole contract document, sent unchanged as the request's rotation. */
  document: Record<string, unknown>
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function readId(value: Record<string, unknown>, name: string): string {
  const id = value[name]
  if (typeof id !== 'string' || id.length === 0) {
    throw new Error(`invalid-rotation-definition:${name}-empty`)
  }
  return id
}

/** Parse and validate the rotation definition example. */
export function parseRotationDefinition(value: unknown): RotationDefinitionExample {
  if (!isRecord(value)) {
    throw new Error('invalid-rotation-definition:not-an-object')
  }
  if (value.contract !== 'rotation_definition') {
    throw new Error('invalid-rotation-definition:contract-not-rotation-definition')
  }
  return {
    case_id: readId(value, 'case_id'),
    field_id: readId(value, 'field_id'),
    rotation_id: readId(value, 'rotation_id'),
    label: readId(value, 'label'),
    document: value,
  }
}

/** The example rotation definition: the one rotation the seam can run. */
export const rotationDefinition: RotationDefinitionExample =
  parseRotationDefinition(rawRotation)
