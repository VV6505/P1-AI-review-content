import { AdminPkbDetail } from "@/features/studio/admin";
export default async function Page({ params }: PageProps<"/admin/pkb/[id]">) { const { id } = await params; return <AdminPkbDetail id={id} />; }
