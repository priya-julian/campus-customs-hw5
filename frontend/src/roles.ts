/** Each agent gets its own identity so the board reads at a glance.
 *
 * Five shades along one blue axis rather than five unrelated hues: the team
 * should look like one team, with the Boss darkest because it is the one that
 * decides and the specialists lighter as they fan outward.
 */
import type { Role } from './types'

export interface RoleStyle {
  label: string
  short: string
  mono: string
  hue: string
  soft: string
  job: string
}

export const ROLES: Record<Role, RoleStyle> = {
  boss: {
    label: 'Boss', short: 'Boss', mono: 'BS', hue: '#13306b', soft: '#e4eaf7',
    job: 'Routes the ticket and makes the final call',
  },
  inventory: {
    label: 'Inventory', short: 'Inv', mono: 'IN', hue: '#1668a8', soft: '#e2f0fa',
    job: 'Stock by SKU and size, shortfalls, restock path',
  },
  accounting: {
    label: 'Accounting', short: 'Acct', mono: 'AC', hue: '#3a53a4', soft: '#e8ebf9',
    job: 'Cash, invoices, margins, approval requests',
  },
  facilities: {
    label: 'Facilities', short: 'Fac', mono: 'FA', hue: '#2b7f8f', soft: '#e2f2f3',
    job: 'The lease, the landlord, rent timing',
  },
  customer_service: {
    label: 'Customer Service', short: 'CS', mono: 'CS', hue: '#5a7fd6', soft: '#ecf0fc',
    job: 'Drafts what the customer reads — never sends',
  },
}

export const ROLE_ORDER: Role[] = ['boss', 'inventory', 'accounting', 'facilities', 'customer_service']

/** Tool names arrive prefixed by the MCP server name; show the bare verb. */
export function prettyTool(tool: string): string {
  return tool.replace(/^campus-customs_/, '').replace(/_/g, ' ')
}
