import { BriefcaseBusiness, Building2, FileText, Target, ClipboardList, FileCheck2, LayoutDashboard, Mail, type LucideIcon } from "lucide-react";
import { type Screen } from "./types";

export const NAV_ITEMS: Array<{
  id: Screen;
  label: string;
  description: string;
  icon: LucideIcon;
}> = [
  {
    id: "overview",
    label: "Overview",
    description: "Your workspace",
    icon: LayoutDashboard,
  },
  {
    id: "jobs",
    label: "Discover jobs",
    description: "Explore opportunities",
    icon: BriefcaseBusiness,
  },
  {
    id: "recommended",
    label: "Recommended",
    description: "Best next actions",
    icon: Target,
  },
  {
    id: "applications",
    label: "Applications",
    description: "Track your pipeline",
    icon: ClipboardList,
  },
  {
    id: "documents",
    label: "Cover letters & answers",
    description: "Honest application writing",
    icon: FileText,
  },
  {
    id: "resume",
    label: "Resume studio",
    description: "Tailor your resume",
    icon: FileCheck2,
  },
  {
    id: "coverage",
    label: "Company coverage",
    description: "Source health",
    icon: Building2,
  },
  {
    id: "email",
    label: "Email intelligence",
    description: "Assessments and interviews",
    icon: Mail,
  },
];
