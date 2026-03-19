interface WorkspaceResizeHandleProps {
  onMouseDown: (event: React.MouseEvent<HTMLDivElement>) => void;
}

export function WorkspaceResizeHandle({ onMouseDown }: WorkspaceResizeHandleProps) {
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      onMouseDown={onMouseDown}
      style={{
        width: "10px",
        cursor: "col-resize",
        position: "relative",
        flexShrink: 0,
      }}
    >
      <div
        style={{
          position: "absolute",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          width: "3px",
          height: "64px",
          borderRadius: "999px",
          background: "rgba(255, 255, 255, 0.18)",
          boxShadow: "0 0 18px rgba(125, 177, 255, 0.15)",
        }}
      />
    </div>
  );
}

export default WorkspaceResizeHandle;
