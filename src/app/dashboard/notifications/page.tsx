import type { Metadata } from "next";
import { PageTitle } from "@/components/dashboard/ui";
import { NotificationsClient } from "@/components/dashboard/notifications/NotificationsClient";
import { FootballAlerts } from "@/components/dashboard/notifications/FootballAlerts";

export const metadata: Metadata = { title: "Notifications" };

export default function Page() {
  return (
    <>
      <PageTitle title="Notifications" sub="Alerts about things in your own records. Nothing is created until you switch an alert on, and everything stays in the app: no email or push is sent." />
      <NotificationsClient />
      <div className="mt-6"><FootballAlerts /></div>
    </>
  );
}
