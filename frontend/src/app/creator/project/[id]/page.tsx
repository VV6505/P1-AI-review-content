import { CreatorStudio } from "@/features/studio/creator";
export default async function Page({ params }: { params: Promise<{ id: string }> }) { const { id } = await params; return <CreatorStudio projectId={id} />; }
