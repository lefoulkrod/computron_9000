import React, { useRef, useState, useEffect } from 'react';
import styles from './ChatInput.module.css';
import PaperclipIcon from './icons/PaperclipIcon.jsx';
import SendIcon from './icons/SendIcon.jsx';
import StopIcon from './icons/StopIcon.jsx';
import ProfileSelector from './ProfileSelector.jsx';
import AttachmentChip from './AttachmentChip.jsx';

/** Approximate decoded byte size of a base64 string. */
function _base64Bytes(b64) {
    const padding = b64.endsWith('==') ? 2 : b64.endsWith('=') ? 1 : 0;
    return Math.max(0, Math.floor(b64.length * 3 / 4) - padding);
}

function ChatInput({ onSend, onStop, isStreaming, attachment, draft, onDraftConsumed, selectedProfileId, onProfileChange, profileRefreshSignal }) {
    const [message, setMessage] = useState('');
    const [selectedProfile, setSelectedProfile] = useState(null);

    const profileName = selectedProfile?.name;
    const placeholder = isStreaming
        ? `Send a nudge${profileName ? ` to ${profileName}` : ''}…`
        : `Message ${profileName || 'Computron'}…`;

    useEffect(() => {
        if (draft) {
            setMessage(draft);
            onDraftConsumed();
        }
    }, [draft, onDraftConsumed]);
    const [fileData, setFileData] = useState(null);
    const [filePreview, setFilePreview] = useState(null);
    const [fileName, setFileName] = useState(null);
    const fileInputRef = useRef(null);

    useEffect(() => {
        if (attachment) {
            const { base64, contentType = 'image/png', filename } = attachment;
            const dataUrl = `data:${contentType};base64,${base64}`;
            setFileData({ base64, content_type: contentType, filename: filename || null });
            if (contentType.startsWith('image/')) {
                setFilePreview(dataUrl);
            } else {
                setFilePreview(null);
            }
            setFileName(filename || null);
            if (fileInputRef.current) {
                fileInputRef.current.value = '';
            }
        }
    }, [attachment]);

    const clearAttachment = () => {
        setFileData(null);
        setFilePreview(null);
        setFileName(null);
        if (fileInputRef.current) fileInputRef.current.value = '';
    };

    const handleSubmit = (e) => {
        e.preventDefault();
        if (!message.trim() && !fileData) return;
        onSend(message.trim(), fileData);
        setMessage('');
        clearAttachment();
    };

    const handleFile = (e) => {
        const file = e.target.files[0];
        if (!file) {
            clearAttachment();
            return;
        }
        const reader = new FileReader();
        reader.onload = (ev) => {
            const base64 = ev.target.result.split(',')[1];
            setFileData({ base64, content_type: file.type, filename: file.name });
            if (file.type.startsWith('image/')) {
                setFilePreview(ev.target.result);
            } else {
                setFilePreview(null);
            }
            setFileName(file.name);
        };
        reader.readAsDataURL(file);
    };

    const handlePaste = (e) => {
        const items = e.clipboardData?.items;
        if (!items) return;
        for (const item of items) {
            if (item.type.startsWith('image/')) {
                e.preventDefault();
                const file = item.getAsFile();
                if (!file) return;
                const reader = new FileReader();
                reader.onload = (ev) => {
                    const base64 = ev.target.result.split(',')[1];
                    const name = `screenshot_${Date.now()}.png`;
                    setFileData({ base64, content_type: file.type, filename: name });
                    setFilePreview(ev.target.result);
                    setFileName(name);
                };
                reader.readAsDataURL(file);
                return;
            }
        }
    };

    const hasAttachment = filePreview || fileName;

    return (
        <div className={styles.inputAreaWrapper}>
            <form className={styles.inputArea} onSubmit={handleSubmit}>
                {hasAttachment && (
                    <div className={styles.tray}>
                        <AttachmentChip
                            src={filePreview || undefined}
                            filename={fileName}
                            sizeBytes={fileData?.base64 ? _base64Bytes(fileData.base64) : undefined}
                            onRemove={clearAttachment}
                        />
                    </div>
                )}
                <textarea
                    className={styles.customInput}
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                            e.preventDefault();
                            handleSubmit(e);
                        }
                    }}
                    onPaste={handlePaste}
                    placeholder={placeholder}
                />
                <div className={styles.inputAreaButtons}>
                    <ProfileSelector
                        selectedId={selectedProfileId}
                        onChange={onProfileChange}
                        disabled={isStreaming}
                        refreshSignal={profileRefreshSignal}
                        onSelectedProfile={setSelectedProfile}
                    />
                    <div className={styles.actionButtons}>
                    <button
                        type="button"
                        id="fileButton"
                        className={styles.iconButton}
                        onClick={() => fileInputRef.current && fileInputRef.current.click()}
                        title="Attach file"
                        aria-label="Attach file"
                    >
                        <PaperclipIcon />
                    </button>
                    <input
                        ref={fileInputRef}
                        type="file"
                        id="fileInput"
                        style={{ display: 'none' }}
                        onClick={(e) => {
                            e.target.value = '';
                        }}
                        onChange={handleFile}
                    />
                    {isStreaming ? (
                        <button
                            type="button"
                            className={`${styles.sendButton} ${styles.stopButton}`}
                            title="Stop generation"
                            aria-label="Stop generation"
                            onClick={onStop}
                        >
                            <StopIcon />
                        </button>
                    ) : (
                        <button
                            type="submit"
                            className={styles.sendButton}
                            title="Send message"
                            aria-label="Send message"
                            disabled={!message.trim() && !fileData}
                        >
                            <SendIcon />
                        </button>
                    )}
                    </div>
                </div>
            </form>
        </div>
    );
}

export default ChatInput;
