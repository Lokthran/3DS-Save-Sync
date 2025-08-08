# 3DS-Save-Sync
A Python-based tool to back up and transfer 3DS, NDS,  GBA and custom save files via FTP.

## Features

-   **Simple Interface:** Easy-to-use GUI built with CustomTkinter.
-   **Manual Control:** Manually trigger downloads (3DS to PC) or uploads (PC to 3DS).
-   **Automatic Backups:** Automatically creates timestamped backups of the destination folder before overwriting.
-   **Dynamic Categories:** Add, remove, and name your own save categories.
-   **Network Scan:** Automatically scans the local network to find your 3DS if no IP is provided.

## How to Use

1.  **Prerequisites:**
    -   A 3DS console with Custom Firmware (Luma3DS) and the Homebrew Launcher.
    -   The `FTPD` homebrew application on your 3DS.
    -   Python 3 installed on your PC.
    -   The `customtkinter` library (`pip install customtkinter`).

2.  **Setup:**
    -   Run the application (`python sync_tool.pyw`).
    -   On first launch, the tool creates a `Saves` folder with default subdirectories.
    -   Configure the paths for your saves in the GUI if you want to use different locations on your PC. The main "Backup Folder" is required.

3.  **Transferring Saves:**
    -   Start `FTPD` on your 3DS.
    -   Launch the tool on your PC.
    -   Enter your 3DS's IP address or leave it blank to scan.
    -   Select the categories you want to sync by enabling them.
    -   Click "Download to PC" or "Upload to 3DS".


**For 3DS Games:** Please use Checkpoint on your console to export your save files first.
