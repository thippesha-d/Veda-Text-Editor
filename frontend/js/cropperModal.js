// frontend/js/cropperModal.js

/**
 * Handles the Cropper.js modal interaction.
 */

let cropperInstance = null;

export function openCropperModal(file, onCropComplete) {
    const modal = document.getElementById('cropper-modal');
    const image = document.getElementById('cropper-image');
    const btnCancel = document.getElementById('cropper-cancel');
    const btnConfirm = document.getElementById('cropper-confirm');

    if (!modal || !image || !btnCancel || !btnConfirm) {
        console.error("Cropper modal elements missing from DOM.");
        // Fallback: just return the file without cropping
        onCropComplete(file);
        return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
        image.src = e.target.result;
        modal.style.display = 'flex';
        
        if (cropperInstance) cropperInstance.destroy();
        
        // Initialize Cropper.js
        cropperInstance = new window.Cropper(image, {
            viewMode: 2,
            autoCropArea: 0.9,
            responsive: true,
            background: false,
        });
    };
    reader.readAsDataURL(file);

    const cleanup = () => {
        modal.style.display = 'none';
        btnCancel.onclick = null;
        btnConfirm.onclick = null;
        if (cropperInstance) {
            cropperInstance.destroy();
            cropperInstance = null;
        }
    };

    btnCancel.onclick = () => {
        cleanup();
    };

    btnConfirm.onclick = () => {
        if (!cropperInstance) return;
        cropperInstance.getCroppedCanvas().toBlob((blob) => {
            const newFile = new File([blob], file.name, { type: file.type || 'image/png' });
            onCropComplete(newFile);
            cleanup();
        }, file.type || 'image/png');
    };
}
