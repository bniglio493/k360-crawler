#!/bin/bash
cd ~/Downloads/k360_crawler\ 4
python3 main.py scrape \
  --districts \
    Lisboa Cascais Oeiras Amadora "Vila Franca de Xira" Loures Sintra Odivelas Mafra \
    Almada Barreiro Moita Montijo Seixal Sesimbra Setubal Palmela Alcochete \
    Albufeira Portimao Lagoa Faro Loule Silves Lagos \
  --portals olx_pt custojusto_pt imovirtual_pt casa_sapo_pt \
  --tipos apartamento moradia terreno \
  --max-pages 10
