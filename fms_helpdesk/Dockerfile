FROM odoo:18

USER root

COPY requirements.txt /tmp/requirements.txt
# odoo:18 is built on Ubuntu Noble (PEP 668): system pip needs --break-system-packages.
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt

COPY . /mnt/extra-addons/fms_helpdesk
RUN chown -R odoo:odoo /mnt/extra-addons/fms_helpdesk

USER odoo
