import {
  Activity,
  Beaker,
  Briefcase,
  FolderKanban,
  History,
  Landmark,
  LayoutGrid,
  LineChart,
  Settings,
  type LucideIcon,
} from "lucide-react";

export interface DashNav {
  label: string;
  href: string;
  icon: LucideIcon;
  keywords: string;
  status?: "live" | "soon";
}

export const DASH_NAV: DashNav[] = [
  { label: "Overview", href: "/dashboard", icon: LayoutGrid, keywords: "home summary", status: "live" },
  { label: "Sports Intelligence", href: "/dashboard/sports", icon: Activity, keywords: "football soccer match fixtures poisson", status: "live" },
  { label: "Business Strategy", href: "/dashboard/business", icon: Briefcase, keywords: "game theory nash payoff pricing", status: "soon" },
  { label: "Political Intelligence", href: "/dashboard/politics", icon: Landmark, keywords: "coalition voting power policy", status: "soon" },
  { label: "Financial Intelligence", href: "/dashboard/finance", icon: LineChart, keywords: "portfolio var risk monte carlo", status: "soon" },
  { label: "Simulation Lab", href: "/dashboard/simulations", icon: Beaker, keywords: "monte carlo seed scenario", status: "soon" },
  { label: "Prediction History", href: "/dashboard/history", icon: History, keywords: "forecasts past saved", status: "live" },
  { label: "My Workspace", href: "/dashboard/workspace", icon: FolderKanban, keywords: "team members organization", status: "live" },
  { label: "Settings", href: "/dashboard/settings", icon: Settings, keywords: "account profile", status: "live" },
];
