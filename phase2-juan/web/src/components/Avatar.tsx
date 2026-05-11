import { Facehash } from 'facehash'

interface Props {
  name: string
  color: string
  size?: number
  enableBlink?: boolean
}

/**
 * Solid single-color Facehash avatar — the default flavor used for chat
 * authors and sidebar agents. Use Facehash directly for gradient variants.
 */
export function Avatar({ name, color, size = 28, enableBlink }: Props) {
  return (
    <Facehash
      name={name}
      size={size}
      variant="solid"
      colors={[color]}
      showInitial={false}
      enableBlink={enableBlink}
    />
  )
}
