import React, { useRef, useState, useEffect } from 'react';
import styles from './ChatInput.module.css';
import PaperclipIcon from './icons/PaperclipIcon.jsx';
import SendIcon from './icons/SendIcon.jsx';
import StopIcon from './icons/StopIcon.jsx';
import ProfileSelector from './ProfileSelector.jsx';

function ChatInput({ onSend, onStop, isStreaming, attachment, draft, onDraftConsumed, selectedProfileId, onProfileChange, profileRefreshSignal }) {
    const [message, setMessage] = useState('');

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
                <div className={styles.customInputWrapper}>
                    {hasAttachment && (
                        <div className={styles.inlinePreview}>
                            {filePreview ? (
                                <img src={filePreview} alt="selected" />
                            ) : (
                                <div className={styles.fileChip}>
                                    <span className={styles.fileChipIcon}>📎</span>
                                    <span className={styles.fileChipName}>{fileName}</span>
                                </div>
                            )}
                            <button
                                type="button"
                                className={styles.removeAttachment}
                                aria-label="Remove attachment"
                                title="Remove attachment"
                                onClick={clearAttachment}
                            >
                                ×
                            </button>
                        </div>
                    )}
                    <textarea
                        className={`${styles.customInput} ${hasAttachment ? styles.withPreview : ''}`}
                        value={message}
                        onChange={(e) => setMessage(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                                e.preventDefault();
                                handleSubmit(e);
                            }
                        }}
                        onPaste={handlePaste}
                        placeholder={isStreaming ? "Send a nudge to the agent..." : "Type your message..."}
                    />
                </div>
                <div className={styles.inputAreaButtons}>
                    <ProfileSelector
                        selectedId={selectedProfileId}
                        onChange={onProfileChange}
                        disabled={isStreaming}
                        refreshSignal={profileRefreshSignal}
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
                    <button
                        type="submit"
                        className={styles.iconButton}
                        title={isStreaming ? "Send nudge" : "Send message"}
                        aria-label={isStreaming ? "Send nudge" : "Send message"}
                    >
                        <SendIcon />
                    </button>
                    {isStreaming && (
                        <button
                            type="button"
                            className={`${styles.iconButton} ${styles.stopButton}`}
                            title="Stop generation"
                            aria-label="Stop generation"
                            onClick={onStop}
                        >
                            <StopIcon />
                        </button>
                    )}
                    </div>
                </div>
            </form>
        </div>
    );
}

export default ChatInput;
