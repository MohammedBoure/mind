import React, { useState, useRef } from 'react';
import { useProjectStore } from './state/projectStore.js';
import { TopNavbar } from './components/TopNavbar.js';
import { Toolbar2D } from './components/Toolbar2D.js';
import { CatalogDrawer } from './components/CatalogDrawer.js';
import { PropertyInspector } from './components/PropertyInspector.js';
import { BoQModal } from './components/BoQModal.js';
import { AlternativesModal } from './components/AlternativesModal.js';
import { ExportModal } from './components/ExportModal.js';
import { BlueprintCanvas } from './engine2d/BlueprintCanvas.js';
import { Viewport3D, Viewport3DHandle } from './engine3d/Viewport3D.js';
import { calculateBoQ } from './core/boqCalculator.js';

export function App() {
  const store = useProjectStore();
  const viewport3DRef = useRef<Viewport3DHandle | null>(null);

  // Modal states
  const [isCatalogOpen, setIsCatalogOpen] = useState(false);
  const [isBoQOpen, setIsBoQOpen] = useState(false);
  const [isAlternativesOpen, setIsAlternativesOpen] = useState(false);
  const [isExportOpen, setIsExportOpen] = useState(false);

  // Live BoQ Total Budget in integer cents
  const currentBoQ = calculateBoQ(store.activeAlt);

  const handleCaptureSnapshot = () => {
    return viewport3DRef.current?.captureSnapshot() || '';
  };

  return (
    <div className="flex flex-col w-screen h-screen bg-slate-950 text-slate-100 overflow-hidden font-sans">
      {/* Top Architectural Studio Navigation Bar */}
      <TopNavbar
        activeAlternative={store.activeAlt}
        alternatives={store.alternatives}
        viewLayout={store.viewLayout}
        isWalkthrough={store.isWalkthrough}
        cutawayMode={store.settings.cutawayMode}
        canUndo={store.canUndo}
        canRedo={store.canRedo}
        totalBudgetCents={currentBoQ.totalCostCents}
        onSelectAlternative={store.switchAlternative}
        onSetViewLayout={store.setViewLayout}
        onToggleWalkthrough={() => store.setIsWalkthrough(!store.isWalkthrough)}
        onToggleCutaway={store.toggleCutaway}
        onUndo={store.undo}
        onRedo={store.redo}
        onOpenBoQ={() => setIsBoQOpen(true)}
        onOpenAlternatives={() => setIsAlternativesOpen(true)}
        onOpenExport={() => setIsExportOpen(true)}
        onResetProject={store.resetProject}
      />

      {/* Main Workspace: Linked 2D & 3D Split Canvas + Inspector */}
      <div className="flex-1 flex overflow-hidden relative">
        {/* Workspace Canvas Container */}
        <div className="flex-1 flex overflow-hidden relative">
          {/* 2D Architectural Blueprint Viewport */}
          {(store.viewLayout === 'split' || store.viewLayout === '2d_only') && (
            <div
              className={`relative h-full ${
                store.viewLayout === 'split'
                  ? 'w-1/2 border-r border-slate-800'
                  : 'w-full'
              }`}
            >
              <Toolbar2D
                editorMode={store.editorMode}
                isCatalogOpen={isCatalogOpen}
                hasSelection={store.selection.type !== 'none'}
                onSetEditorMode={store.setEditorMode}
                onToggleCatalog={() => setIsCatalogOpen(!isCatalogOpen)}
                onDeleteSelected={store.deleteSelected}
              />

              <CatalogDrawer
                isOpen={isCatalogOpen}
                onClose={() => setIsCatalogOpen(false)}
                onSelectItem={(catalogId) => {
                  store.setPendingCatalogItem(catalogId);
                  store.setEditorMode('place_furniture');
                }}
              />

              <BlueprintCanvas
                vertices={store.activeAlt.vertices}
                walls={store.activeAlt.walls}
                openings={store.activeAlt.openings}
                furniture={store.activeAlt.furniture}
                rooms={store.activeAlt.rooms}
                selection={store.selection}
                editorMode={store.editorMode}
                pendingCatalogItem={store.pendingCatalogItem}
                doorConflicts={store.doorConflicts}
                collidingFurnitureIds={store.collidingFurnitureIds}
                onSelect={store.setSelection}
                onAddWall={store.addWall}
                onUpdateVertex={store.updateVertex}
                onAddOpening={store.addOpening}
                onUpdateOpeningOffset={(id, offset) => store.updateOpening(id, { offset })}
                onAddFurniture={store.addFurniture}
                onUpdateFurniture={store.updateFurniture}
                onDeleteSelected={store.deleteSelected}
              />
            </div>
          )}

          {/* 3D Interactive WebGL Viewport */}
          {(store.viewLayout === 'split' || store.viewLayout === '3d_only') && (
            <div
              className={`relative h-full ${
                store.viewLayout === 'split' ? 'w-1/2' : 'w-full'
              }`}
            >
              <Viewport3D
                ref={viewport3DRef}
                vertices={store.activeAlt.vertices}
                walls={store.activeAlt.walls}
                openings={store.activeAlt.openings}
                furniture={store.activeAlt.furniture}
                rooms={store.activeAlt.rooms}
                selection={store.selection}
                isWalkthrough={store.isWalkthrough}
                cutawayMode={store.settings.cutawayMode}
                onSelect={store.setSelection}
                onToggleWalkthrough={store.setIsWalkthrough}
              />
            </div>
          )}
        </div>

        {/* Real-time Contextual Property Inspector */}
        <PropertyInspector
          selection={store.selection}
          walls={store.activeAlt.walls}
          openings={store.activeAlt.openings}
          furniture={store.activeAlt.furniture}
          rooms={store.activeAlt.rooms}
          doorConflicts={store.doorConflicts}
          collidingFurnitureIds={store.collidingFurnitureIds}
          onUpdateWall={store.updateWall}
          onUpdateOpening={store.updateOpening}
          onUpdateFurniture={store.updateFurniture}
          onUpdateRoom={store.updateRoom}
          onDeleteSelected={store.deleteSelected}
          onClose={() => store.setSelection({ type: 'none', id: null })}
        />
      </div>

      {/* Modals */}
      <BoQModal
        isOpen={isBoQOpen}
        activeAlternative={store.activeAlt}
        onClose={() => setIsBoQOpen(false)}
      />

      <AlternativesModal
        isOpen={isAlternativesOpen}
        activeAlternative={store.activeAlt}
        alternatives={store.alternatives}
        onSelectAlternative={store.switchAlternative}
        onBranchAlternative={store.branchAlternative}
        onClose={() => setIsAlternativesOpen(false)}
      />

      <ExportModal
        isOpen={isExportOpen}
        activeAlternative={store.activeAlt}
        alternatives={store.alternatives}
        settings={store.settings}
        onClose={() => setIsExportOpen(false)}
        onCaptureSnapshot={handleCaptureSnapshot}
        onImportProject={store.loadProjectData}
      />
    </div>
  );
}
export default App;
