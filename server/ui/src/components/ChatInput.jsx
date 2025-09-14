import React, { useRef, useState } from 'react';
import styles from './ChatInput.module.css';

export default function ChatInput({ onSend, disabled }) {
  const [message, setMessage] = useState('');
  const [fileData, setFileData] = useState(null);
  const [filePreview, setFilePreview] = useState(null);
  const fileInputRef = useRef(null);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (disabled) return;
    onSend(message.trim(), fileData);
    setMessage('');
    setFileData(null);
    setFilePreview(null);
    if (fileInputRef.current) {
      // Reset the file input so selecting the same file again fires onChange
      fileInputRef.current.value = null;
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
          placeholder="Type your message..."
          disabled={disabled}
        />
        {filePreview && (
          <div
            className={styles.inputImageWrapper}
            onClick={() => {
              setFileData(null);
              setFilePreview(null);
              if (fileInputRef.current) fileInputRef.current.value = null;
            }}
          >
            <img src={filePreview} alt="selected" />
          </div>
        )}
        <div className={styles.inputAreaButtons}>
          <button
            type="button"
            id="fileButton"
            onClick={() => fileInputRef.current && fileInputRef.current.click()}
            disabled={disabled}
          >
            File
          </button>
          <input
            ref={fileInputRef}
            type="file"
            id="fileInput"
            style={{ display: 'none' }}
            accept="image/*"
            onClick={(e) => {
              // Clearing here ensures selecting the same file triggers onChange
              e.target.value = null;
            }}
            onChange={handleFile}
          />
          <button type="submit" disabled={disabled}>Send</button>
        </div>
      </form>
    </div>
  );
}
