import { openDB } from 'idb';

const DB_NAME = 'TerraWatchOfflineDB';
const STORE_NAME = 'offlineReports';

export async function initDB() {
    return openDB(DB_NAME, 1, {
        upgrade(db) {
            if (!db.objectStoreNames.contains(STORE_NAME)) {
                db.createObjectStore(STORE_NAME, { keyPath: 'id', autoIncrement: true });
            }
        },
    });
}

export async function saveReportOffline(reportData) {
    const db = await initDB();
    await db.add(STORE_NAME, {
        ...reportData,
        timestamp: Date.now()
    });
}

export async function getOfflineReports() {
    const db = await initDB();
    return db.getAll(STORE_NAME);
}

export async function removeOfflineReport(id) {
    const db = await initDB();
    await db.delete(STORE_NAME, id);
}

export async function syncOfflineReports() {
    const reports = await getOfflineReports();
    if (reports.length === 0) return 0;

    let synced = 0;
    for (const report of reports) {
        try {
            const formData = new FormData();
            formData.append('description', report.description);
            formData.append('latitude', report.latitude);
            formData.append('longitude', report.longitude);

            const res = await fetch('/api/report', {
                method: 'POST',
                body: formData,
            });

            if (res.ok) {
                await removeOfflineReport(report.id);
                synced++;
            }
        } catch (err) {
            console.warn("Offline report sync failed for id:", report.id, err);
        }
    }
    return synced;
}
