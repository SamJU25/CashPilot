import { redirect } from 'next/navigation';

/** Approvals live in the Assistant's side panel; next.config.js redirects too, this covers direct renders. */
export default function ApprovalsPage() {
  redirect('/assistant');
}
