import { Suspense, lazy } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { Skeleton } from '@/components/Skeleton';
import { AppLayout } from '@/layouts/AppLayout';
import { EventLayout } from '@/layouts/EventLayout';

const LoginPage = lazy(() =>
  import('@/pages/LoginPage').then((m) => ({ default: m.LoginPage })),
);
const DashboardPage = lazy(() =>
  import('@/pages/DashboardPage').then((m) => ({ default: m.DashboardPage })),
);
const EventsListPage = lazy(() =>
  import('@/pages/EventsListPage').then((m) => ({ default: m.EventsListPage })),
);
const EventOverviewPage = lazy(() =>
  import('@/pages/EventOverviewPage').then((m) => ({ default: m.EventOverviewPage })),
);
const EventSummaryPage = lazy(() =>
  import('@/pages/EventSummaryPage').then((m) => ({ default: m.EventSummaryPage })),
);
const EventFilesPage = lazy(() =>
  import('@/pages/EventFilesPage').then((m) => ({ default: m.EventFilesPage })),
);
const EventComtradePage = lazy(() =>
  import('@/pages/EventComtradePage').then((m) => ({ default: m.EventComtradePage })),
);
const WaveformPage = lazy(() =>
  import('@/pages/WaveformPage').then((m) => ({ default: m.WaveformPage })),
);
const TimelinePage = lazy(() =>
  import('@/pages/TimelinePage').then((m) => ({ default: m.TimelinePage })),
);
const FaultCharacteristicsPage = lazy(() =>
  import('@/pages/FaultCharacteristicsPage').then((m) => ({
    default: m.FaultCharacteristicsPage,
  })),
);
const FaultLocationPage = lazy(() =>
  import('@/pages/FaultLocationPage').then((m) => ({ default: m.FaultLocationPage })),
);
const ChannelMappingPage = lazy(() =>
  import('@/pages/ChannelMappingPage').then((m) => ({ default: m.ChannelMappingPage })),
);
const DigitalTargetsPage = lazy(() =>
  import('@/pages/DigitalTargetsPage').then((m) => ({ default: m.DigitalTargetsPage })),
);
const DrWorkspacePage = lazy(() =>
  import('@/pages/DrWorkspacePage').then((m) => ({ default: m.DrWorkspacePage })),
);
const ElectricalPage = lazy(() =>
  import('@/pages/ElectricalPage').then((m) => ({ default: m.ElectricalPage })),
);
const ProtectionPage = lazy(() =>
  import('@/pages/ProtectionPage').then((m) => ({ default: m.ProtectionPage })),
);
const ConsistencyPage = lazy(() =>
  import('@/pages/ConsistencyPage').then((m) => ({ default: m.ConsistencyPage })),
);
const RcaPage = lazy(() =>
  import('@/pages/RcaPage').then((m) => ({ default: m.RcaPage })),
);
const EvidencePage = lazy(() =>
  import('@/pages/EvidencePage').then((m) => ({ default: m.EvidencePage })),
);
const ReportPage = lazy(() =>
  import('@/pages/ReportPage').then((m) => ({ default: m.ReportPage })),
);
const ReviewPage = lazy(() =>
  import('@/pages/ReviewPage').then((m) => ({ default: m.ReviewPage })),
);
const UploadPage = lazy(() =>
  import('@/pages/UploadPage').then((m) => ({ default: m.UploadPage })),
);
const UsersPage = lazy(() =>
  import('@/pages/UsersPage').then((m) => ({ default: m.UsersPage })),
);
const AuditPage = lazy(() =>
  import('@/pages/AuditPage').then((m) => ({ default: m.AuditPage })),
);
const CreateEventPage = lazy(() =>
  import('@/pages/CreateEventPage').then((m) => ({ default: m.CreateEventPage })),
);
const HelpPage = lazy(() =>
  import('@/pages/HelpPage').then((m) => ({ default: m.HelpPage })),
);
const CompareEventsPage = lazy(() =>
  import('@/pages/CompareEventsPage').then((m) => ({ default: m.CompareEventsPage })),
);

function RouteFallback() {
  return <Skeleton rows={6} label="Loading page" />;
}

export default function App() {
  return (
    <Suspense fallback={<RouteFallback />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        <Route element={<ProtectedRoute />}>
          <Route path="/events/:id/waveforms/popout" element={<WaveformPage popout />} />

          <Route element={<AppLayout />}>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/events" element={<EventsListPage />} />
            <Route path="/events/compare" element={<CompareEventsPage />} />
            <Route path="/events/new" element={<CreateEventPage />} />
            <Route path="/upload" element={<UploadPage />} />
            <Route path="/help" element={<HelpPage />} />
            <Route path="/users" element={<UsersPage />} />
            <Route path="/audit" element={<AuditPage />} />

            <Route path="/events/:id" element={<EventLayout />}>
              <Route index element={<Navigate to="summary" replace />} />
              <Route path="overview" element={<EventOverviewPage />} />
              <Route path="summary" element={<EventSummaryPage />} />
              <Route path="files" element={<EventFilesPage />} />
              <Route path="comtrade" element={<EventComtradePage />} />
              <Route path="channel-map" element={<ChannelMappingPage />} />
              <Route path="digital-map" element={<DigitalTargetsPage />} />
              <Route path="dr" element={<DrWorkspacePage />} />
              <Route path="waveforms" element={<WaveformPage />} />
              <Route path="timeline" element={<TimelinePage />} />
              <Route path="fault-characteristics" element={<FaultCharacteristicsPage />} />
              <Route path="fault-location" element={<FaultLocationPage />} />
              <Route path="electrical" element={<ElectricalPage />} />
              <Route path="protection" element={<ProtectionPage />} />
              <Route path="consistency" element={<ConsistencyPage />} />
              <Route path="rca" element={<RcaPage />} />
              <Route path="evidence" element={<EvidencePage />} />
              <Route path="report" element={<ReportPage />} />
              <Route path="review" element={<ReviewPage />} />
            </Route>
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/dashboard" />} />
      </Routes>
    </Suspense>
  );
}
