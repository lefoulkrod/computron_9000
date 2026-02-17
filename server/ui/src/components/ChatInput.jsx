import React, { useRef, useState, useEffect } from 'react';
import styles from './ChatInput.module.css';
import PaperclipIcon from './icons/PaperclipIcon.jsx';
import SendIcon from './icons/SendIcon.jsx';

function ChatInput({ onSend, disabled, attachment }) {
    const [message, setMessage] = useState('');
    const [fileData, setFileData] = useState(null);
    const [filePreview, setFilePreview] = useState(null);
    const fileInputRef = useRef(null);

    useEffect(() => {
        if (attachment) {
            const { base64, contentType = 'image/png' } = attachment;
            const dataUrl = `data:${contentType};base64,${base64}`;
            setFileData({ base64, content_type: contentType });
            setFilePreview(dataUrl);
            if (fileInputRef.current) {
                fileInputRef.current.value = '';
            }
        }
    }, [attachment]);

    const handleSubmit = (e) => {
        e.preventDefault();
        if (disabled) return;
        onSend(message.trim(), fileData);
        setMessage('');
        setFileData(null);
        setFilePreview(null);
        if (fileInputRef.current) {
            // Reset the file input so selecting the same file again fires onChange
            fileInputRef.current.value = '';
        }
    };

    const handleFile = (e) => {
        const file = e.target.files[0];
        if (!file) {
            setFileData(null);
            setFilePreview(null);
            return;
        }
        const reader = new FileReader();
        reader.onload = (ev) => {
            const base64 = ev.target.result.split(',')[1];
            setFileData({ base64, content_type: file.type });
            if (file.type.startsWith('image/')) {
                setFilePreview(ev.target.result);
            } else {
                setFilePreview(null);
            }
        };
        reader.readAsDataURL(file);
    };

    return (
        <div className={styles.inputAreaWrapper}>
            <form className={styles.inputArea} onSubmit={handleSubmit}>
                <div className={styles.customInputWrapper}>
                    {filePreview && (
                        <div className={styles.inlinePreview}>
                            <img src={filePreview} alt="selected" />
                            <button
                                type="button"
                                className={styles.removeAttachment}
                                aria-label="Remove image"
                                title="Remove image"
                                onClick={() => {
                                    setFileData(null);
                                    setFilePreview(null);
                                    if (fileInputRef.current) fileInputRef.current.value = '';
                                }}
                            >
                                ×
                            </button>
                        </div>
                    )}
                    <textarea
                        className={`${styles.customInput} ${filePreview ? styles.withPreview : ''}`}
                        value={message}
                        onChange={(e) => setMessage(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                                e.preventDefault();
                                handleSubmit(e);
                            }
                        }}
                        placeholder="Type your message..."
                        disabled={disabled}
                    />
                </div>
                <div className={styles.inputAreaButtons}>
                    <button
                        type="button"
                        id="fileButton"
                        className={styles.iconButton}
                        onClick={() => fileInputRef.current && fileInputRef.current.click()}
                        title="Attach file"
                        aria-label="Attach file"
                        disabled={disabled}
                    >
                        <PaperclipIcon />
                    </button>
                    <input
                        ref={fileInputRef}
                        type="file"
                        id="fileInput"
                        style={{ display: 'none' }}
                        accept="image/*"
                        onClick={(e) => {
                            // Clearing here ensures selecting the same file triggers onChange
                            e.target.value = '';
                        }}
                        onChange={handleFile}
                    />
                    <button
                        type="submit"
                        className={styles.iconButton}
                        title="Send message"
                        aria-label="Send message"
                        disabled={disabled}
                    >
                        <SendIcon />
                    </button>
                </div>
            </form>
        </div>
    );
}

export default ChatInput;
