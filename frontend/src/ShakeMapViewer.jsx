import React, { useEffect, useState } from 'react';
import { MapContainer, TileLayer, GeoJSON, Tooltip, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';

const INTENSITY_COLORS = [
    { min: 7, color: '#4a148c', label: 'Severe (VII+)' },
    { min: 6, color: '#b71c1c', label: 'Strong (VI)' },
    { min: 5, color: '#f44336', label: 'Moderate-Strong (V)' },
    { min: 4, color: '#ff9800', label: 'Moderate (IV)' },
    { min: 0, color: '#ffd54f', label: 'Light (III)' },
];

function getColor(intensity) {
    for (const { min, color } of INTENSITY_COLORS) {
        if (intensity >= min) return color;
    }
    return '#ffd54f';
}

function MapFitter({ geojson }) {
    const map = useMap();
    useEffect(() => {
        if (!geojson || !geojson.features || geojson.features.length === 0) return;
        let minLat = 90, maxLat = -90, minLng = 180, maxLng = -180;
        geojson.features.forEach(f => {
            f.geometry.coordinates[0].forEach(([lng, lat]) => {
                if (lng < minLng) minLng = lng;
                if (lng > maxLng) maxLng = lng;
                if (lat < minLat) minLat = lat;
                if (lat > maxLat) maxLat = lat;
            });
        });
        if (minLat < maxLat && minLng < maxLng) {
            map.fitBounds([[minLat, minLng], [maxLat, maxLng]], { padding: [24, 24], maxZoom: 9 });
        }
    }, [geojson, map]);
    return null;
}

export function ShakeMapViewer({ eventId, eventPlace, eventMag, impactStr }) {
    const [grid, setGrid] = useState(null);
    const [loading, setLoading] = useState(false);
    const [totalAffected, setTotalAffected] = useState(null);

    useEffect(() => {
        if (!eventId) return;
        setGrid(null);
        setTotalAffected(null);
        setLoading(true);
        fetch(`/api/shakemap/${eventId}`)
            .then(res => res.json())
            .then(data => {
                if (data.type === 'FeatureCollection') {
                    setGrid(data);
                    const sum = data.features.reduce((acc, f) => acc + (f.properties.population_affected || 0), 0);
                    setTotalAffected(sum);
                }
            })
            .catch(err => console.error('ShakeMap grid fetch error:', err))
            .finally(() => setLoading(false));
    }, [eventId]);

    const styleCell = (feature) => ({
        fillColor: getColor(feature.properties.intensity),
        weight: 0,
        fillOpacity: 0.65,
    });

    if (!eventId) return null;

    return (
        <div style={{
            marginTop: '20px',
            background: 'linear-gradient(135deg, #0d1117 0%, #161b22 100%)',
            border: '1px solid rgba(255,179,0,0.25)',
            borderRadius: '10px',
            padding: '16px',
            boxShadow: '0 4px 24px rgba(0,0,0,0.5)',
        }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px', gap: '12px', flexWrap: 'wrap' }}>
                <div>
                    <div style={{ color: '#ffb300', fontWeight: 700, fontSize: '12px', letterSpacing: '1.5px', textTransform: 'uppercase', marginBottom: '4px' }}>
                        ⚡ Live ShakeMap × WorldPop Overlay
                    </div>
                    {eventPlace && (
                        <div style={{ color: '#e8eaf6', fontSize: '14px', fontWeight: 500 }}>
                            M{eventMag} — {eventPlace}
                        </div>
                    )}
                </div>
                <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                    {(totalAffected || impactStr) && (
                        <div style={{
                            background: 'rgba(244, 67, 54, 0.15)',
                            border: '1px solid rgba(244,67,54,0.5)',
                            borderRadius: '6px',
                            padding: '8px 14px',
                            textAlign: 'center',
                        }}>
                            <div style={{ color: '#ff7675', fontSize: '11px', letterSpacing: '1px', marginBottom: '2px' }}>EST. EXPOSED</div>
                            <div style={{ color: '#fff', fontWeight: 700, fontSize: '18px' }}>
                                {impactStr || (totalAffected ? totalAffected.toLocaleString() : '—')}
                            </div>
                            <div style={{ color: '#aaa', fontSize: '11px' }}>people in shaking zone</div>
                        </div>
                    )}
                    {totalAffected && (
                        <div style={{
                            background: 'rgba(255, 152, 0, 0.12)',
                            border: '1px solid rgba(255,152,0,0.4)',
                            borderRadius: '6px',
                            padding: '8px 14px',
                            textAlign: 'center',
                        }}>
                            <div style={{ color: '#ffb300', fontSize: '11px', letterSpacing: '1px', marginBottom: '2px' }}>GRID CELLS</div>
                            <div style={{ color: '#fff', fontWeight: 700, fontSize: '18px' }}>
                                {grid ? grid.features.length : '—'}
                            </div>
                            <div style={{ color: '#aaa', fontSize: '11px' }}>5-km tiles analysed</div>
                        </div>
                    )}
                </div>
            </div>

            {/* Map */}
            <div style={{ height: '340px', width: '100%', borderRadius: '6px', overflow: 'hidden', position: 'relative' }}>
                {loading && (
                    <div style={{
                        position: 'absolute', inset: 0, zIndex: 1000,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        background: 'rgba(13,17,23,0.75)',
                        color: '#ffb300', fontSize: '14px', fontWeight: 600, letterSpacing: '1px'
                    }}>
                        LOADING GRID...
                    </div>
                )}
                <MapContainer center={[20, 0]} zoom={2}
                    style={{ height: '100%', width: '100%' }}
                    zoomControl={true} scrollWheelZoom={false}>
                    <TileLayer
                        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
                        attribution='&copy; <a href="https://carto.com">CARTO</a>'
                    />
                    {grid && (
                        <>
                            <GeoJSON
                                key={`grid-${eventId}`}
                                data={grid}
                                style={styleCell}
                                onEachFeature={(feature, layer) => {
                                    layer.bindTooltip(
                                        `Intensity: ${feature.properties.intensity.toFixed(1)}<br/>Pop. affected: ${feature.properties.population_affected.toLocaleString()}`,
                                        { sticky: true, className: 'shake-tooltip' }
                                    );
                                }}
                            />
                            <MapFitter geojson={grid} />
                        </>
                    )}
                </MapContainer>
            </div>

            {/* Legend */}
            <div style={{ display: 'flex', gap: '8px', marginTop: '10px', flexWrap: 'wrap' }}>
                {INTENSITY_COLORS.map(({ color, label }) => (
                    <div key={label} style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '11px', color: '#bbb' }}>
                        <div style={{ width: 12, height: 12, borderRadius: 2, background: color, opacity: 0.85, flexShrink: 0 }} />
                        {label}
                    </div>
                ))}
            </div>
        </div>
    );
}
